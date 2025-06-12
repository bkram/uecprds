package main

import (
	"log"
	"time"

	"uecprds/pkg/uecprds"
)

func main() {
	rds := uecprds.New("/dev/ttyUSB0", 9600, time.Second)
	if err := rds.Open(); err != nil {
		log.Fatalf("open serial: %v", err)
	}
	defer rds.Close()

	// Example frame - in a real application build a proper UECP frame.
	frame := []byte{0x00, 0x00}
	if err := rds.Send(frame); err != nil {
		log.Fatalf("send: %v", err)
	}
}
