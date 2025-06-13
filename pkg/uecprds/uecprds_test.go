package uecprds

import (
	"encoding/hex"
	"testing"
	"time"
)

func TestBuildFramePS(t *testing.T) {
	u := New("", 9600, 0, 0x1337, 15, true, true, false, 0x00, false)
	group := u.buildGroup(0x02, []byte("DEMO    "))
	frame := u.buildFrame(group)
	got := hex.EncodeToString(frame)
	want := "fe0000000b02000044454d4f202020209180ff"
	if got != want {
		t.Fatalf("PS frame mismatch\nwant %s\n got %s", want, got)
	}
}

func TestBuildFrameTP(t *testing.T) {
	u := New("", 9600, 0, 0x1337, 15, true, true, false, 0x00, false)
	group := u.buildGroup(0x03, []byte{0x02})
	frame := u.buildFrame(group)
	got := hex.EncodeToString(frame)
	want := "fe0000000403000002fc59ff"
	if got != want {
		t.Fatalf("TP frame mismatch\nwant %s\n got %s", want, got)
	}
}

func TestBuildFramePI(t *testing.T) {
	u := New("", 9600, 0, 0x1337, 15, true, true, false, 0x00, false)
	group := u.buildGroup(0x01, []byte{0x13, 0x37})
	frame := u.buildFrame(group)
	got := hex.EncodeToString(frame)
	want := "fe0000000501000013371e49ff"
	if got != want {
		t.Fatalf("PI frame mismatch\nwant %s\n got %s", want, got)
	}
}

func TestBuildFramePTY(t *testing.T) {
	u := New("", 9600, 0, 0x1337, 15, true, true, false, 0x00, false)
	group := u.buildGroup(0x07, []byte{0x0f})
	frame := u.buildFrame(group)
	got := hex.EncodeToString(frame)
	want := "fe000000040700000fe705ff"
	if got != want {
		t.Fatalf("PTY frame mismatch\nwant %s\n got %s", want, got)
	}
}

func TestBuildFrameMS(t *testing.T) {
	u := New("", 9600, 0, 0x1337, 15, true, true, false, 0x00, false)
	group := u.buildGroup(0x05, []byte{0x01})
	frame := u.buildFrame(group)
	got := hex.EncodeToString(frame)
	want := "fe0000000405000001eba3ff"
	if got != want {
		t.Fatalf("MS frame mismatch\nwant %s\n got %s", want, got)
	}
}

func TestBuildFrameDI(t *testing.T) {
	u := New("", 9600, 0, 0x1337, 15, true, true, false, 0x00, false)
	group := u.buildGroup(0x04, []byte{0x00})
	frame := u.buildFrame(group)
	got := hex.EncodeToString(frame)
	want := "fe00000004040000008d36ff"
	if got != want {
		t.Fatalf("DI frame mismatch\nwant %s\n got %s", want, got)
	}
}

func TestBuildFrameAF(t *testing.T) {
	u := New("", 9600, 0, 0x1337, 15, true, true, false, 0x00, false)
	payload := u.buildAFPayload([]float64{92.4})
	if payload == nil {
		t.Fatal("nil AF payload")
	}
	group := u.buildGroup(0x13, payload)
	frame := u.buildFrame(group)
	got := hex.EncodeToString(frame)
	want := "fe0000000a130000050000e1310060643bff"
	if got != want {
		t.Fatalf("AF frame mismatch\nwant %s\n got %s", want, got)
	}
}

func TestBuildFrameCTProfline(t *testing.T) {
	u := New("", 9600, 0, 0x1337, 15, true, true, false, 0x00, false)
	tstamp := time.Date(2023, 8, 25, 12, 34, 56, 0, time.UTC)
	payload := []byte{byte(tstamp.Year() % 100), byte(tstamp.Month()), byte(tstamp.Day()), byte(tstamp.Hour()), byte(tstamp.Minute()), byte(tstamp.Second()), 0x00, 0x00}
	group := u.buildGroup(0x0D19, payload)
	frame := u.buildFrame(group)
	got := hex.EncodeToString(frame)
	want := "fe0000000b0d19001708190c22380000337dff"
	if got != want {
		t.Fatalf("CT frame mismatch\nwant %s\n got %s", want, got)
	}
}
