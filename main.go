package main

import (
	"encoding/binary"
	"fmt"
	"gopkg.in/yaml.v3"
	"io"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/tarm/serial" // Reverted back to tarm/serial
)

// Config struct mirrors the YAML configuration
type Config struct {
	Serial struct {
		Port        string  `yaml:"port"`
		Baudrate    int     `yaml:"baudrate"`
		DelaySeconds float64 `yaml:"delay_seconds"`
	} `yaml:"serial"`
	Station struct {
		ProgramIdentificationCode int  `yaml:"program_identification_code"`
		ProgramTypeCode         int  `yaml:"program_type_code"`
		RdsMusicFlag            bool `yaml:"rds_music_flag"`
		Tp                      bool `yaml:"tp"`
		Ta                      bool `yaml:"ta"`
	} `yaml:"station"`
	Flags struct {
		Di struct {
			Stereo        bool `yaml:"stereo"`
			ArtificialHead bool `yaml:"artificial_head"`
			Compressed    bool `yaml:"compressed"`
			DynamicPty    bool `yaml:"dynamic_pty"`
		} `yaml:"di"`
	} `yaml:"flags"`
	Display struct {
		Ps struct {
			Texts             []string `yaml:"texts"`
			Center            bool     `yaml:"center"`
			ScrollEnabled     bool     `yaml:"scroll_enabled"`
			ScrollBidirectional bool   `yaml:"scroll_bidirectional"`
			ScrollSpeedSeconds float64  `yaml:"scroll_speed_seconds"`
			DisplayDelaySeconds float64 `yaml:"display_delay_seconds"`
		} `yaml:"ps"`
		Rt struct {
			Messages          []string `yaml:"messages"`
			File              string   `yaml:"file"`
			Center            bool     `yaml:"center"`
			ChangeIntervalSeconds float64 `yaml:"change_interval_seconds"`
		} `yaml:"rt"`
	} `yaml:"display"`
	Clock struct {
		Enable        bool    `yaml:"enable"`
		IntervalSeconds float64 `yaml:"interval_seconds"`
	} `yaml:"clock"`
	Af struct {
		Enable           bool    `yaml:"enable"`
		AlternateFrequencies []float64 `yaml:"alternate_frequencies"`
	} `yaml:"af"`
}

// LoadConfig reads the YAML configuration file
func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}
	var cfg Config
	err = yaml.Unmarshal(data, &cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}
	return &cfg, nil
}

// Summary returns a string summary of the configuration
func (c *Config) Summary() string {
	diFlags := fmt.Sprintf("S=%d, AH=%d, C=%d, DP=%d",
		boolToInt(c.Flags.Di.Stereo),
		boolToInt(c.Flags.Di.ArtificialHead),
		boolToInt(c.Flags.Di.Compressed),
		boolToInt(c.Flags.Di.DynamicPty),
	)
	return fmt.Sprintf(
		"Serial: %s @ %d bps\n"+
			"PI: 0x%04X, PTY: %d, MS: %t\n"+
			"TP: %t, TA: %t, DI: %s\n"+
			"PS entries: %d, RT entries: %d\n"+
			"AF enabled: %t (%d entries)\n"+
			"Clock enabled: %t (interval %.1fs)",
		c.Serial.Port, c.Serial.Baudrate,
		c.Station.ProgramIdentificationCode, c.Station.ProgramTypeCode, c.Station.RdsMusicFlag,
		c.Station.Tp, c.Station.Ta, diFlags,
		len(c.Display.Ps.Texts), len(c.Display.Rt.Messages),
		c.Af.Enable, len(c.Af.AlternateFrequencies),
		c.Clock.Enable, c.Clock.IntervalSeconds,
	)
}

// boolToInt converts a boolean to an integer (0 or 1)
func boolToInt(b bool) int {
	if b {
		return 1
	}
	return 0
}

// UECPRDS handles UECP communication with the RDS encoder.
type UECPRDS struct {
	port      string
	baudrate  int
	delay     time.Duration
	pi        int
	pty       int
	ms        bool
	tp        bool
	ta        bool
	di        byte
	debug     bool
	serialPort io.ReadWriteCloser
}

// NewUECPRDS creates a new UECPRDS instance.
func NewUECPRDS(cfg *Config, debug bool) *UECPRDS {
	di := byte(
		(boolToInt(cfg.Flags.Di.Stereo) << 0) |
			(boolToInt(cfg.Flags.Di.ArtificialHead) << 1) |
			(boolToInt(cfg.Flags.Di.Compressed) << 2) |
			(boolToInt(cfg.Flags.Di.DynamicPty) << 3),
	)

	return &UECPRDS{
		port:     cfg.Serial.Port,
		baudrate: cfg.Serial.Baudrate,
		delay:    time.Duration(cfg.Serial.DelaySeconds * float64(time.Second)),
		pi:       cfg.Station.ProgramIdentificationCode,
		pty:      cfg.Station.ProgramTypeCode,
		ms:       cfg.Station.RdsMusicFlag,
		tp:       cfg.Station.Tp,
		ta:       cfg.Station.Ta,
		di:       di,
		debug:    debug,
	}
}

// openSerialPort opens the serial port.
func (u *UECPRDS) openSerialPort() error {
	if u.serialPort != nil {
		return nil // Already open
	}
	c := &serial.Config{Name: u.port, Baud: u.baudrate, ReadTimeout: time.Second}
	s, err := serial.OpenPort(c)
	if err != nil {
		return fmt.Errorf("failed to open serial port: %w", err)
	}
	u.serialPort = s
	return nil
}

// closeSerialPort closes the serial port.
func (u *UECPRDS) closeSerialPort() {
	if u.serialPort != nil {
		u.serialPort.Close()
		u.serialPort = nil
	}
}

// SendStaticInit sends TP/TA, PI, PTY, MS and DI frames to initialise the encoder.
func (u *UECPRDS) SendStaticInit() {
	u.SendTPTA()
	u.SendPI()
	u.SendPTY()
	u.SendMS()
	u.SendDI()
}

// SendAF sends alternate frequencies.
func (u *UECPRDS) SendAF(afList []float64) {
	payload, err := u.buildAFPayload(afList)
	if err != nil {
		log.Printf("Error building AF payload: %v", err)
		return
	}
	u.sendMessage(u.buildGroup(0x13, payload))
}

// SendPS sends Program Service name.
func (u *UECPRDS) SendPS(text string) {
	ps := text
	if len(ps) > 8 {
		ps = ps[:8]
	}
	for len(ps) < 8 {
		ps += " " // Pad to 8 characters
	}
	u.sendMessage(u.buildGroup(0x02, []byte(ps)))
}

// SendRT sends Radiotext message.
func (u *UECPRDS) SendRT(text string) {
	rtData := []byte(text)
	if len(rtData) > 64 {
		rtData = rtData[:64]
	}
	for len(rtData) < 64 {
		rtData = append(rtData, ' ') // Pad to 64 characters
	}
	payload := append([]byte{0x41, 0x00}, rtData...)
	u.sendMessage(u.buildGroup(0x0A, payload))
}

// SendCTProfline sends clock time using the Profline proprietary group.
// Based on the provided "valid CT dump", the format is:
// MEC: 0x0D19, Group Type: 0x06
// Data: Day, Hour, Minute, Second, 0x00, 0x00 (6 bytes total)
func (u *UECPRDS) SendCTProfline(dt time.Time) {
	// Build the *entire* message payload (MEC + GroupType + Data)
	// MEC 0x0D19 is two bytes (0x0D, 0x19)
	// Group Type is 0x06 (as observed in the valid dump)
	// Data is 6 bytes: Day, Hour, Minute, Second, 0x00, 0x00
	ctPayload := []byte{
		0x0D,       // MEC MSB
		0x19,       // MEC LSB
		0x06,       // Group Type (as observed in valid dump)
		byte(dt.Day()),    // Day
		byte(dt.Hour()),   // Hour
		byte(dt.Minute()), // Minute
		byte(dt.Second()), // Second
		0x00, 0x00,        // Two padding bytes
	}

	u.sendMessage(ctPayload) // sendMessage expects the full (MEC+GroupType+Data) payload
}

// SendTPTA sends the Traffic Program and Traffic Announcement flags.
func (u *UECPRDS) SendTPTA() {
	val := byte((boolToInt(u.tp) << 1) | boolToInt(u.ta))
	u.sendMessage(u.buildGroup(0x03, []byte{val}))
}

// SendPI sends the Program Identification code.
func (u *UECPRDS) SendPI() {
	piBytes := make([]byte, 2)
	binary.BigEndian.PutUint16(piBytes, uint16(u.pi))
	u.sendMessage(u.buildGroup(0x01, piBytes))
}

// SendPTY sends the Program Type code.
func (u *UECPRDS) SendPTY() {
	u.sendMessage(u.buildGroup(0x07, []byte{byte(u.pty)}))
}

// SendMS sends the Music/Speech flag.
func (u *UECPRDS) SendMS() {
	u.sendMessage(u.buildGroup(0x05, []byte{byte(boolToInt(u.ms))}))
}

// SendDI sends the Decoder Information byte.
func (u *UECPRDS) SendDI() {
	u.sendMessage(u.buildGroup(0x04, []byte{u.di}))
}

// buildAFPayload builds the AF payload based on the number of frequencies.
func (u *UECPRDS) buildAFPayload(afList []float64) ([]byte, error) {
	encodedAFs := make([]byte, 0, len(afList))
	for _, f := range afList {
		encoded, err := u.encodeAF(f)
		if err != nil {
			log.Printf("[AF ENCODE ERROR] %.1f MHz skipped: %v", f, err)
			continue
		}
		encodedAFs = append(encodedAFs, encoded)
	}

	switch {
	case len(encodedAFs) == 1:
		return u.buildAFMethod05(encodedAFs), nil
	case len(encodedAFs) >= 2 && len(encodedAFs) <= 3:
		return u.buildAFMethod07(encodedAFs), nil
	case len(encodedAFs) >= 4 && len(encodedAFs) <= 11:
		return u.buildAFMethod0F(encodedAFs), nil
	default:
		return nil, fmt.Errorf("invalid AF list length: %d", len(encodedAFs))
	}
}

// encodeAF encodes a frequency in MHz to an AF code.
func (u *UECPRDS) encodeAF(freqMHz float64) (byte, error) {
	if freqMHz < 87.6 || freqMHz > 107.9 {
		return 0, fmt.Errorf("AF %.1f MHz outside valid range (87.6-107.9)", freqMHz)
	}
	afCode := int(round(freqMHz*10 - 875)) // Correct calculation for AF code
	if afCode < 1 || afCode > 204 {
		return 0, fmt.Errorf("AF code %d invalid.", afCode)
	}
	return byte(afCode), nil
}

func round(f float64) float64 {
	return float64(int(f + 0.5))
}

func (u *UECPRDS) buildAFMethod05(encodedAFs []byte) []byte {
	payload := []byte{0x05, 0x00, 0x00, 0xE1}
	payload = append(payload, encodedAFs[0])
	payload = append(payload, 0x00, 0x60)
	return payload
}

func (u *UECPRDS) buildAFMethod07(encodedAFs []byte) []byte {
	payload := []byte{0x07, 0x00, 0x00}
	payload = append(payload, 0xE0+byte(len(encodedAFs)))
	payload = append(payload, encodedAFs...)
	for len(payload) < 7 { // Pad to 3 AFs + 4 bytes header (0x07 0x00 0x00 0xE_ AF1 AF2 AF3)
		payload = append(payload, 0x00)
	}
	if len(encodedAFs) == 2 {
		payload = append(payload, 0x00, 0xD3)
	} else { // len(encodedAFs) == 3
		payload = append(payload, 0x00, 0xEE)
	}
	return payload
}

// buildAFMethod0F creates the AF payload for Method 0F (4-11 AFs)
func (u *UECPRDS) buildAFMethod0F(encodedAFs []byte) []byte {
	payload := []byte{0x0F, 0x00, 0x00, 0xEB} // Header for Method 0F
	payload = append(payload, encodedAFs...)

	// Ensure payload has enough space for 11 AF positions (4 header + 11 AF positions = 15 bytes)
	for len(payload) < 4+11 {
		payload = append(payload, 0x00) // Pad remaining AF positions with zeros
	}
	payload = append(payload, 0x00, 0xAC) // Append the fixed trailing 0x00 0xAC

	return payload
}

// buildGroup builds a UECP group (MEC + GroupType + Data).
// For MECs > 0xFF, the MEC is 2 bytes, then GroupType is 1 byte, then data.
// For MECs <= 0xFF, the MEC is 1 byte, then GroupType is 1 byte (0x00 for standard), then a padding byte (0x00), then data.
// Note: SendCTProfline builds its message manually due to Profline's specific GroupType for 0x0D19.
func (u *UECPRDS) buildGroup(mec int, data []byte) []byte {
    var header []byte
    if mec > 0xFF { // Handles 2-byte MECs, assuming GroupType 0x00 for these (except custom CT)
        header = []byte{byte((mec >> 8) & 0xFF), byte(mec & 0xFF), 0x00}
    } else { // Handles 1-byte MECs (like 0x01, 0x02, etc.)
        // This structure is MEC (1 byte), GroupType (1 byte, default 0x00), 3rd byte (0x00 reserved), then data.
        header = []byte{byte(mec), 0x00, 0x00}
    }
    return append(header, data...)
}


// sendMessage writes a prepared UECP group to the serial port.
func (u *UECPRDS) sendMessage(msg []byte) {
	if err := u.openSerialPort(); err != nil {
		log.Printf("Error opening serial port for message: %v", err)
		return
	}
	defer u.closeSerialPort() // Close after each message if it's not a long-lived connection

	frame := u.buildFrame(msg)
	if u.debug {
		log.Printf("[UECP HEX] %X", frame)
	}

	_, err := u.serialPort.Write(frame)
	if err != nil {
		log.Printf("Failed to write to serial port: %v", err)
		return
	}
	// The type assertion is safe because serial.OpenPort always returns *serial.Port,
	// which has the Flush method.
	err = u.serialPort.(*serial.Port).Flush()
	if err != nil {
		log.Printf("Failed to flush serial port: %v", err)
	}
	time.Sleep(u.delay)
}

// buildFrame builds a complete UECP frame.
func (u *UECPRDS) buildFrame(msg []byte) []byte {
	// The length byte is len(msg), which is MEC + GroupType + Data
	header := []byte{0x00, 0x00, 0x00, byte(len(msg))}
	payload := append(header, msg...)
	crc := u.crc16(payload, 0x1021, 0xFFFF)
	full := append(payload, byte(crc>>8), byte(crc&0xFF))
	stuffed := u.byteStuff(full)
	return append([]byte{0xFE}, append(stuffed, 0xFF)...)
}

// crc16 calculates the CRC-16-CCITT checksum.
func (u *UECPRDS) crc16(data []byte, poly, init uint16) uint16 {
	crc := init
	for _, b := range data {
		crc ^= uint16(b) << 8
		for i := 0; i < 8; i++ {
			if crc&0x8000 != 0 {
				crc = (crc << 1) ^ poly
			} else {
				crc <<= 1
			}
		}
	}
	return crc ^ 0xFFFF
}

// byteStuff performs byte stuffing.
func (u *UECPRDS) byteStuff(data []byte) []byte {
	stuffed := make([]byte, 0, len(data)*2)
	for _, b := range data {
		stuffed = append(stuffed, b)
		if b == 0xFE || b == 0xFF {
			stuffed = append(stuffed, 0xFD)
		}
	}
	return stuffed
}

// RDSDaemon orchestrates the RDS data transmission.
type RDSDaemon struct {
	config      *Config
	debug       bool
	rds         *UECPRDS
	scrollFrames []string
	stopChan    chan struct{}
	wg          chan struct{} // Using a channel as a wait group for simplicity
}

// NewRDSDaemon creates a new RDSDaemon instance.
func NewRDSDaemon(cfg *Config, debug bool) *RDSDaemon {
	daemon := &RDSDaemon{
		config:   cfg,
		debug:    debug,
		stopChan: make(chan struct{}),
		wg:       make(chan struct{}, 3), // Max 3 workers (PS, RT, CT)
	}
	daemon.rds = NewUECPRDS(cfg, debug)
	daemon.scrollFrames = daemon.generatePSScroll()
	return daemon
}

// generatePSScroll generates PS scroll frames.
func (d *RDSDaemon) generatePSScroll() []string {
	names := d.config.Display.Ps.Texts
	text := strings.Join(names, " ")
	text = strings.TrimSpace(text)
	text = strings.ReplaceAll(text, "  ", " ") // Replace double spaces with single

	width := 8
	if !d.config.Display.Ps.ScrollEnabled || len(text) <= width {
		return []string{}
	}

	frames := []string{}
	if !d.config.Display.Ps.ScrollBidirectional {
		data := text + " " + text[:width-1]
		for i := 0; i <= len(data)-width; i++ {
			frames = append(frames, data[i:i+width])
		}
	} else {
		for i := 0; i <= len(text)-width; i++ {
			frames = append(frames, text[i:i+width])
		}
		for i := len(text) - width - 1; i >= 0; i-- {
			frames = append(frames, text[i:i+width])
		}
	}
	return frames
}

// safeSendPS sends a PS message.
func (d *RDSDaemon) safeSendPS(text string) {
	d.rds.SendPS(text)
	log.Printf("Sent PS: %s", text)
}

// safeSendRT sends an RT message.
func (d *RDSDaemon) safeSendRT(text string) {
	d.rds.SendRT(text)
	log.Printf("Sent RT: %s", text)
}

// psWorker handles PS transmission.
func (d *RDSDaemon) psWorker() {
	defer func() { d.wg <- struct{}{} }() // Signal completion
	idx := 0
	for {
		select {
		case <-d.stopChan:
			return
		default:
			if len(d.scrollFrames) > 0 {
				frame := d.scrollFrames[idx%len(d.scrollFrames)]
				idx++
				text := frame
				if d.config.Display.Ps.Center {
					text = centerString(frame, 8)
				} else {
					text = padRight(frame, 8)
				}
				d.safeSendPS(text)
				select {
				case <-d.stopChan:
					return
				case <-time.After(time.Duration(d.config.Display.Ps.ScrollSpeedSeconds * float64(time.Second))):
					// Continue
				}
			} else {
				for _, ps := range d.config.Display.Ps.Texts {
					text := ps
					if d.config.Display.Ps.Center {
						text = centerString(ps, 8)
					} else {
						text = padRight(ps, 8)
					}
					d.safeSendPS(text)
					select {
					case <-d.stopChan:
						return
					case <-time.After(time.Duration(d.config.Display.Ps.DisplayDelaySeconds * float64(time.Second))):
						// Continue
					}
				}
			}
		}
	}
}

// rtWorker handles RT transmission.
func (d *RDSDaemon) rtWorker() {
	defer func() { d.wg <- struct{}{} }() // Signal completion
	idx := 0
	for {
		select {
		case <-d.stopChan:
			return
		default:
			currentRTText := ""
			if d.config.Display.Rt.File != "" && fileExists(d.config.Display.Rt.File) {
				content, err := os.ReadFile(d.config.Display.Rt.File)
				if err != nil {
					log.Printf("Warning: Error reading RT file '%s': %v. Falling back to default message.", d.config.Display.Rt.File, err)
					if len(d.config.Display.Rt.Messages) > 0 {
						currentRTText = d.config.Display.Rt.Messages[0]
					}
				} else {
					currentRTText = strings.TrimSpace(string(content))
					if currentRTText == "" && len(d.config.Display.Rt.Messages) > 0 {
						currentRTText = d.config.Display.Rt.Messages[0]
					}
				}
			} else {
				if len(d.config.Display.Rt.Messages) > 0 {
					currentRTText = d.config.Display.Rt.Messages[idx%len(d.config.Display.Rt.Messages)]
					idx++
				}
			}

			if currentRTText == "" {
				if d.config.Display.Rt.File != "" && !fileExists(d.config.Display.Rt.File) {
					currentRTText = "NO RT FILE OR MESSAGES"
				} else {
					currentRTText = "RADIO TEXT" // Default safe string
				}
			}

			textToSend := currentRTText
			if d.config.Display.Rt.Center {
				textToSend = centerString(currentRTText, 64)
			} else {
				textToSend = padRight(currentRTText, 64)
			}

			d.safeSendRT(textToSend)
			select {
			case <-d.stopChan:
				return
			case <-time.After(time.Duration(d.config.Display.Rt.ChangeIntervalSeconds * float64(time.Second))):
				// Continue
			}
		}
	}
}

// ctWorker handles Clock Time transmission.
func (d *RDSDaemon) ctWorker() {
	defer func() { d.wg <- struct{}{} }() // Signal completion
	for {
		select {
		case <-d.stopChan:
			return
		default:
			now := time.Now()
			d.rds.SendCTProfline(now)
			log.Println("Sent Profline CT")
			select {
			case <-d.stopChan:
				return
			case <-time.After(time.Duration(d.config.Clock.IntervalSeconds * float64(time.Second))):
				// Continue
			}
		}
	}
}

// Run starts the RDS daemon.
func (d *RDSDaemon) Run() {
	log.Println("Initializing RDS daemon...")
	d.rds.SendStaticInit()
	log.Printf("TP=%t, TA=%t, DI=0x%02X", d.config.Station.Tp, d.config.Station.Ta, d.rds.di)

	if d.config.Af.Enable {
		d.rds.SendAF(d.config.Af.AlternateFrequencies)
		log.Printf("AF frequencies sent: %v", d.config.Af.AlternateFrequencies)
	}

	go d.psWorker()
	go d.rtWorker()
	if d.config.Clock.Enable {
		go d.ctWorker()
	}

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	select {
	case <-sigChan:
		log.Println("Interrupted, shutting down...")
		close(d.stopChan) // Signal workers to stop
	}

	// Wait for all workers to finish
	numWorkers := 2
	if d.config.Clock.Enable {
		numWorkers = 3
	}
	for i := 0; i < numWorkers; i++ {
		<-d.wg
	}
	log.Println("Daemon exited.")
}

// Helper functions for string formatting
func centerString(s string, width int) string {
	if len(s) >= width {
		return s[:width]
	}
	padding := width - len(s)
	left := padding / 2
	right := padding - left
	return strings.Repeat(" ", left) + s + strings.Repeat(" ", right)
}

func padRight(s string, width int) string {
	if len(s) >= width {
		return s[:width]
	}
	return s + strings.Repeat(" ", width-len(s))
}

func fileExists(filename string) bool {
	info, err := os.Stat(filename)
	if os.IsNotExist(err) {
		return false
	}
	return !info.IsDir()
}

func main() {
	// Basic argument parsing
	var cfgPath string
	debug := false
	for i, arg := range os.Args {
		if arg == "--cfg" && i+1 < len(os.Args) {
			cfgPath = os.Args[i+1]
		}
		if arg == "--debug" {
			debug = true
		}
	}

	if cfgPath == "" {
		fmt.Println("Usage: go run main.go --cfg <config_file.yaml> [--debug]")
		os.Exit(1)
	}

	// Set up logging
	log.SetOutput(os.Stdout)
	log.SetFlags(log.Ldate | log.Ltime | log.Lshortfile)

	cfg, err := LoadConfig(cfgPath)
	if err != nil {
		log.Fatalf("Fatal error loading config: %v", err)
	}

	log.Println("Config loaded successfully.")
	log.Println("\n" + cfg.Summary())

	daemon := NewRDSDaemon(cfg, debug)
	daemon.Run()
}