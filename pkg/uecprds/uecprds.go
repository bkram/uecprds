package uecprds

import (
	"time"

	"go.bug.st/serial"
)

// UECPRDS closely mirrors the Python implementation. It handles UECP framing
// and sends groups over a serial connection.
type UECPRDS struct {
	device string
	baud   int
	delay  time.Duration
	pi     int
	pty    int
	ms     bool
	tp     bool
	ta     bool
	di     byte
	debug  bool
	port   serial.Port
}

// New returns a new UECPRDS instance.
func New(device string, baud int, delay time.Duration, pi, pty int, ms, tp, ta bool, di byte, debug bool) *UECPRDS {
	return &UECPRDS{
		device: device,
		baud:   baud,
		delay:  delay,
		pi:     pi,
		pty:    pty,
		ms:     ms,
		tp:     tp,
		ta:     ta,
		di:     di,
		debug:  debug,
	}
}

// Open opens the serial port if not already open.
func (u *UECPRDS) Open() error {
	if u.port != nil {
		return nil
	}
	mode := &serial.Mode{BaudRate: u.baud}
	p, err := serial.Open(u.device, mode)
	if err != nil {
		return err
	}
	u.port = p
	return nil
}

// Close closes the port if open.
func (u *UECPRDS) Close() error {
	if u.port == nil {
		return nil
	}
	err := u.port.Close()
	u.port = nil
	return err
}

// SendStaticInit sends TP/TA, PI, PTY, MS and DI frames.
func (u *UECPRDS) SendStaticInit() error {
	if err := u.SendTPTA(); err != nil {
		return err
	}
	if err := u.SendPI(); err != nil {
		return err
	}
	if err := u.SendPTY(); err != nil {
		return err
	}
	if err := u.SendMS(); err != nil {
		return err
	}
	return u.SendDI()
}

// SendAF sends alternative frequencies encoded like the Python implementation.
func (u *UECPRDS) SendAF(list []float64) error {
	payload := u.buildAFPayload(list)
	if payload == nil {
		return nil
	}
	return u.sendMessage(u.buildGroup(0x13, payload))
}

// SendPS sends the program service text.
func (u *UECPRDS) SendPS(text string) error {
	ps := []byte(text)
	if len(ps) > 8 {
		ps = ps[:8]
	}
	for len(ps) < 8 {
		ps = append(ps, ' ')
	}
	return u.sendMessage(u.buildGroup(0x02, ps))
}

// SendRT sends radiotext.
func (u *UECPRDS) SendRT(text string) error {
	rt := []byte(text)
	if len(rt) > 64 {
		rt = rt[:64]
	}
	for len(rt) < 64 {
		rt = append(rt, ' ')
	}
	payload := append([]byte{0x41, 0x00}, rt...)
	return u.sendMessage(u.buildGroup(0x0A, payload))
}

// SendCTProfline sends the proprietary Profline clock group.
func (u *UECPRDS) SendCTProfline(t time.Time) error {
	payload := []byte{
		byte(t.Year() % 100),
		byte(t.Month()),
		byte(t.Day()),
		byte(t.Hour()),
		byte(t.Minute()),
		byte(t.Second()),
		0x00, 0x00,
	}
	return u.sendMessage(u.buildGroup(0x0D19, payload))
}

// SendTPTA sends the TP and TA flags.
func (u *UECPRDS) SendTPTA() error {
	val := byte(0)
	if u.tp {
		val |= 0x02
	}
	if u.ta {
		val |= 0x01
	}
	return u.sendMessage(u.buildGroup(0x03, []byte{val}))
}

// SendPI sends the PI code.
func (u *UECPRDS) SendPI() error {
	return u.sendMessage(u.buildGroup(0x01, []byte{byte(u.pi >> 8), byte(u.pi)}))
}

// SendPTY sends the program type.
func (u *UECPRDS) SendPTY() error {
	return u.sendMessage(u.buildGroup(0x07, []byte{byte(u.pty)}))
}

// SendMS sends the music/speech flag.
func (u *UECPRDS) SendMS() error {
	b := byte(0)
	if u.ms {
		b = 1
	}
	return u.sendMessage(u.buildGroup(0x05, []byte{b}))
}

// SendDI sends the decoder information byte.
func (u *UECPRDS) SendDI() error {
	return u.sendMessage(u.buildGroup(0x04, []byte{u.di}))
}

func (u *UECPRDS) buildAFPayload(list []float64) []byte {
	enc := make([]byte, 0, len(list))
	for _, f := range list {
		code, err := u.encodeAF(f)
		if err != nil {
			continue
		}
		enc = append(enc, code)
	}
	switch l := len(enc); {
	case l == 1:
		p := []byte{0x05, 0x00, 0x00, 0xE1, enc[0], 0x00, 0x60}
		return p
	case l >= 2 && l <= 3:
		p := []byte{0x07, 0x00, 0x00, 0xE0 + byte(l)}
		p = append(p, enc...)
		for len(p) < 4+3 {
			p = append(p, 0x00)
		}
		if l == 2 {
			p = append(p, 0x00, 0xD3)
		} else {
			p = append(p, 0x00, 0xEE)
		}
		return p
	case l >= 4 && l <= 11:
		p := []byte{0x0F, 0x00, 0x00, 0xEB}
		p = append(p, enc...)
		for len(enc) < 11 {
			enc = append(enc, 0x00)
		}
		p = append(p, enc[len(enc)-11:]...)
		p = append(p, 0x00, 0xAC)
		return p
	default:
		return nil
	}
}

func (u *UECPRDS) encodeAF(freq float64) (byte, error) {
	if freq < 87.6 || freq > 107.9 {
		return 0, errInvalidAF
	}
	code := int((freq-87.5)*10 + 0.5)
	if code < 1 || code > 204 {
		return 0, errInvalidAF
	}
	return byte(code), nil
}

var errInvalidAF = &AFError{"invalid AF"}

type AFError struct{ s string }

func (e *AFError) Error() string { return e.s }

func (u *UECPRDS) sendMessage(msg []byte) error {
	frame := u.buildFrame(msg)
	if u.debug {
		// hex output similar to Python version
		// not using fmt.Printf to avoid import when debug is false
		serialDebug(frame)
	}
	return u.sendGroup(frame)
}

func serialDebug(b []byte) {
	// simplified hex logger to avoid pulling in fmt unless used
	for i, v := range b {
		if i%16 == 0 {
			print("\n")
		}
		print(" ", hexByte(v))
	}
	print("\n")
}

func hexByte(v byte) string {
	const hex = "0123456789ABCDEF"
	return string([]byte{hex[v>>4], hex[v&0x0F]})
}

func (u *UECPRDS) buildGroup(mec int, data []byte) []byte {
	if mec > 0xFF {
		return append([]byte{byte(mec >> 8), byte(mec), 0x00}, data...)
	}
	return append([]byte{byte(mec), 0x00, 0x00}, data...)
}

func (u *UECPRDS) buildFrame(msg []byte) []byte {
	header := []byte{0x00, 0x00, 0x00, byte(len(msg))}
	payload := append(header, msg...)
	crc := crc16(payload)
	full := append(payload, byte(crc>>8), byte(crc))
	stuffed := byteStuff(full)
	return append([]byte{0xFE}, append(stuffed, 0xFF)...)
}

func crc16(data []byte) uint16 {
	crc := uint16(0xFFFF)
	for _, b := range data {
		crc ^= uint16(b) << 8
		for i := 0; i < 8; i++ {
			if crc&0x8000 != 0 {
				crc = (crc << 1) ^ 0x1021
			} else {
				crc <<= 1
			}
			crc &= 0xFFFF
		}
	}
	return crc ^ 0xFFFF
}

func byteStuff(data []byte) []byte {
	out := make([]byte, 0, len(data))
	for _, b := range data {
		out = append(out, b)
		if b == 0xFE || b == 0xFF {
			out = append(out, 0xFD)
		}
	}
	return out
}

func (u *UECPRDS) sendGroup(frame []byte) error {
	if err := u.Open(); err != nil {
		return err
	}
	if _, err := u.port.Write(frame); err != nil {
		return err
	}
	if err := u.port.Flush(); err != nil {
		return err
	}
	time.Sleep(u.delay)
	return nil
}
