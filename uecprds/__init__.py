import serial
import time


class UECPRDS:
    """
    UECPRDS Class

    Encapsulates RDS (Radio Data System) parameters and UECP (Universal Encoder Communication Protocol)
    framing for serial transmission. This class provides methods to configure RDS parameters, build UECP
    frames, and send them over a serial connection.

    Attributes:
        port (str): Serial port to use for communication. Default is "/dev/ttyUSB0".
        baudrate (int): Baud rate for the serial connection. Default is 9600.
        delay (float): Delay between sending frames in seconds. Default is 4.0.
        addr (int): Address of the UECP encoder. Default is 0.
        pi (int): Program Identification (PI) code. Default is 0x0000.
        ps (str): Program Service (PS) name. Default is "DEFAULT".
        rt (str): Radiotext (RT) message. Default is "RADIOTEXT".
        pty (int): Program Type (PTY) code. Default is 0.
        ms (bool): Music/Speech switch. Default is True.
        tp (bool): Traffic Program (TP) flag. Default is False.
        ta (bool): Traffic Announcement (TA) flag. Default is False.

    Methods:
        set_pi(pi: int):
            Sets the Program Identification (PI) code.

        set_ps(ps: str):
            Sets the Program Service (PS) name.

        set_rt(rt: str):
            Sets the Radiotext (RT) message.

        set_pty(pty: int):
            Sets the Program Type (PTY) code. The value is masked to 5 bits.

        set_ms(ms: bool):
            Sets the Music/Speech (MS) switch.

        set_tp(tp: bool):
            Sets the Traffic Program (TP) flag.

        set_ta(ta: bool):
            Sets the Traffic Announcement (TA) flag.

        set_serial(port: str, baudrate: int, delay: float = None):
            Configures the serial port, baud rate, and optional delay.

        _crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
            Computes the CRC-16-CCITT checksum for the given data.

        _build_uecp_frame(msg: bytes) -> bytes:
            Builds a UECP frame for the given message, including header, payload, CRC, and byte stuffing.

        build_rds_messages() -> list[bytes]:
            Constructs a list of RDS messages based on the current parameters.

        build_frames() -> list[bytes]:
            Builds a list of UECP frames from the RDS messages.

        send_all():
            Sends all UECP frames over the configured serial connection with a delay between frames.

        send_single(msg: bytes):
            Sends a single UECP frame for the given message over the configured serial connection.
    """

    """Encapsulates RDS parameters and UECP framing for serial transmission."""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        delay: float = 4.0,
        pi: int = 0x0000,
        ps: str = "DEFAULT",
        rt: str = "RADIOTEXT",
        pty: int = 0,
        ms: bool = True,
        tp: bool = False,
        ta: bool = False,
        addr: int = 0,
    ):
        self.port = port
        self.baudrate = baudrate
        self.delay = delay
        self.addr = addr
        self.pi = pi
        self.ps = ps
        self.rt = rt
        self.pty = pty & 0x1F
        self.ms = ms
        self.tp = tp
        self.ta = ta

    def set_pi(self, pi: int):
        self.pi = pi

    def set_ps(self, ps: str):
        self.ps = ps

    def set_rt(self, rt: str):
        self.rt = rt

    def set_pty(self, pty: int):
        self.pty = pty & 0x1F

    def set_ms(self, ms: bool):
        self.ms = ms

    def set_tp(self, tp: bool):
        self.tp = tp

    def set_ta(self, ta: bool):
        self.ta = ta

    def set_serial(self, port: str, baudrate: int, delay: float = None):
        self.port = port
        self.baudrate = baudrate
        if delay is not None:
            self.delay = delay

    @staticmethod
    def _crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
        crc = init
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                crc = (
                    ((crc << 1) ^ poly) & 0xFFFF
                    if crc & 0x8000
                    else (crc << 1) & 0xFFFF
                )
        return crc ^ 0xFFFF

    def _build_uecp_frame(self, msg: bytes) -> bytes:
        hdr = self.addr.to_bytes(2, "big") + bytes([0x00, len(msg)])
        payload = hdr + msg
        crc = self._crc16_ccitt(payload)
        framed = payload + crc.to_bytes(2, "big")
        stuffed = bytearray()
        for b in framed:
            stuffed.append(b)
            if b in (0xFE, 0xFF):
                stuffed.append(0xFD)
        return b"\xfe" + bytes(stuffed) + b"\xff"

    def build_rds_messages(self) -> list[bytes]:
        msgs = []
        ta_tp = (1 if self.tp else 0) << 1 | (1 if self.ta else 0)
        msgs.append(bytes([0x03, 0x00, 0x00, ta_tp]))
        msgs.append(bytes([0x01, 0x00, 0x00]) + self.pi.to_bytes(2, "big"))
        msgs.append(bytes([0x07, 0x00, 0x00, self.pty]))
        msgs.append(bytes([0x05, 0x00, 0x00, 1 if self.ms else 0]))
        rt_bytes = self.rt.encode("latin-1", "replace")[:64].ljust(64, b" ")
        msgs.append(bytes([0x0A, 0x00, 0x00, 0x41, 0x00]) + rt_bytes)
        ps8 = self.ps[:8].ljust(8)
        msgs.append(bytes([0x02, 0x00, 0x00]) + ps8.encode("ascii", "ignore"))
        return msgs

    def build_frames(self) -> list[bytes]:
        return [self._build_uecp_frame(m) for m in self.build_rds_messages()]

    def send_all(self):
        with serial.Serial(self.port, self.baudrate, timeout=1) as ser:
            for frame in self.build_frames():
                ser.write(frame)
                ser.flush()
                time.sleep(self.delay)

    def send_single(self, msg: bytes):
        with serial.Serial(self.port, self.baudrate, timeout=1) as ser:
            ser.write(self._build_uecp_frame(msg))
            ser.flush()
