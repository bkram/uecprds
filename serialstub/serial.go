package serial

// Minimal stub of go.bug.st/serial

type Mode struct {
	BaudRate int
}

type Port interface {
	Write([]byte) (int, error)
	Flush() error
	Close() error
}

type dummyPort struct{}

func (d *dummyPort) Write(b []byte) (int, error) { return len(b), nil }
func (d *dummyPort) Flush() error                { return nil }
func (d *dummyPort) Close() error                { return nil }

// Open returns a no-op serial port implementation.
func Open(name string, m *Mode) (Port, error) {
	return &dummyPort{}, nil
}
