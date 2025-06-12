package uecprds

import (
	"time"

	"go.bug.st/serial"
)

// UECPRDS provides minimal UECP RDS encoder implementation.
type UECPRDS struct {
	device string
	baud   int
	delay  time.Duration
	port   serial.Port
}

// New returns a new UECPRDS instance configured for the given serial settings.
func New(device string, baud int, delay time.Duration) *UECPRDS {
	return &UECPRDS{device: device, baud: baud, delay: delay}
}

// Open opens the configured serial port.
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

// Close closes the serial port if it is open.
func (u *UECPRDS) Close() error {
	if u.port != nil {
		err := u.port.Close()
		u.port = nil
		return err
	}
	return nil
}

// sendGroup writes the provided frame to the serial port.
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

// Send exposes sendGroup for external callers.
func (u *UECPRDS) Send(frame []byte) error {
	return u.sendGroup(frame)
}
