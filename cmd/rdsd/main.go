package main

import (
	"log"
	"time"

	"uecprds/pkg/uecprds"
)

func main() {
	rds := uecprds.New("/dev/ttyUSB0", 9600, time.Second, 0x1337, 15, true, true, false, 0x00, false)
	if err := rds.SendStaticInit(); err != nil {
		log.Fatalf("init: %v", err)
	}
	if err := rds.SendPS("DEMO"); err != nil {
		log.Fatalf("ps: %v", err)
	}
}
