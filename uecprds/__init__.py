import serial
import time
from datetime import datetime, timezone


class UECPRDS:
    debug = False
    """
    UECPRDS manages UECP-framed RDS commands for serial communication with RDS encoders.

    This updated version sends an initial sequence on instantiation that matches your captured dump order,
    and retains all original setter methods for backward compatibility.
    """

    def __init__(
        self,
        addr=0,
        port="/dev/ttyUSB0",
        baudrate=9600,
        delay=4.0,
        pi=0xFFFF,
        ps="",
        rt="",
        pty=0,
        ms=True,
        tp=False,
        ta=False,
        di=0,
        af=None,
    ):
        self.addr = addr
        self.port = port
        self.baudrate = baudrate
        self.delay = delay

        # RDS data fields
        self.pi = pi
        self.last_pi = None
        self.ps = ps
        self.last_ps = None
        self.rt = rt
        self.last_rt = None
        self.pty = pty & 0x1F
        self.last_pty = None
        self.ms = ms
        self.last_ms = None
        self.tp = tp
        self.ta = ta
        self.last_tp_ta = None
        self.di = di & 0x0F
        self.last_di = None
        self.af = af or []
        self.last_af = None

        # Test serial port availability
        try:
            with serial.Serial(self.port, self.baudrate, timeout=1):
                pass
            time.sleep(0.1)
        except serial.SerialException:
            pass

        # Send the dump-order sequence upon initialization
        self.send_on_init(force=True)

    # --- Setter methods (backward compatible) ---
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

    def set_addr(self, addr: int):
        self.addr = addr

    def set_di(self, di: int):
        self.di = di & 0x0F

    def set_af(self, af_list):
        self.af = list(af_list)

    @staticmethod
    def _crc16_ccitt(data: bytes, poly=0x1021, init=0xFFFF) -> int:
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

    # --- Message builders ---
    def build_pi_message(self) -> bytes:
        return bytes([0x01, 0x00, 0x00]) + self.pi.to_bytes(2, "big")

    def build_ps_message(self) -> bytes:
        ps8 = self.ps[:8].ljust(8)
        return bytes([0x02, 0x00, 0x00]) + ps8.encode("ascii", "ignore")

    def build_rt_message(self) -> bytes:
        rt_bytes = self.rt.encode("latin-1", "replace")[:64].ljust(64, b" ")
        return bytes([0x0A, 0x00, 0x00, 0x41, 0x00]) + rt_bytes

    def build_pty_message(self) -> bytes:
        return bytes([0x07, 0x00, 0x00, self.pty])

    def build_ms_message(self) -> bytes:
        return bytes([0x05, 0x00, 0x00, 1 if self.ms else 0])

    def build_tp_ta_message(self) -> bytes:
        ta_tp = (1 if self.tp else 0) << 1 | (1 if self.ta else 0)
        return bytes([0x03, 0x00, 0x00, ta_tp])

    def build_di_message(self) -> bytes:
        return bytes([0x04, 0x00, 0x00, self.di])

    def _encode_af(self, freq_khz: int) -> int:
        return max(1, min(204, int(round((freq_khz - 87500) / 100)) + 1))

    def build_af_message(self) -> bytes:
        codes = [self._encode_af(f) for f in self.af]
        return bytes([0x14, 0x00, 0x00, len(codes)]) + bytes(codes)

    def build_ct_message(self) -> bytes:
        """
        Stub for CT group (0x19). You should implement UECP clock/time encoding here
        to match your captured CT bytes (e.g. 0x19 + time data).
        """
        # Example placeholder: all zeros
        return bytes([0x19, 0x00, 0x00] + [0] * 9)

    # --- Sending primitives ---
    def send_single(self, msg: bytes):
        frame = self._build_uecp_frame(msg)
        if self.debug:
            print(f"[DEBUG] Full serial frame: {frame.hex()}")
        with serial.Serial(self.port, self.baudrate, timeout=1) as ser:
            ser.write(frame)
            ser.flush()

    def send_pi(self, force=False):
        if force or self.pi != self.last_pi:
            self.send_single(self.build_pi_message())
            self.last_pi = self.pi

    def send_ps(self, force=False):
        if force or self.ps != self.last_ps:
            self.send_single(self.build_ps_message())
            self.last_ps = self.ps

    def send_rt(self, force=False):
        if force or self.rt != self.last_rt:
            self.send_single(self.build_rt_message())
            self.last_rt = self.rt

    def send_pty(self, force=False):
        if force or self.pty != self.last_pty:
            self.send_single(self.build_pty_message())
            self.last_pty = self.pty

    def send_ms(self, force=False):
        if force or self.ms != self.last_ms:
            self.send_single(self.build_ms_message())
            self.last_ms = self.ms

    def send_tp_ta(self, force=False):
        current = (self.tp, self.ta)
        if force or current != self.last_tp_ta:
            self.send_single(self.build_tp_ta_message())
            self.last_tp_ta = current

    def send_di(self, force=False):
        if force or self.di != self.last_di:
            self.send_single(self.build_di_message())
            self.last_di = self.di

    def send_af(self, force=False):
        if force or self.af != self.last_af:
            self.send_single(self.build_af_message())
            self.last_af = list(self.af)

    def send_ct(self, force=False):
        if force:
            self.send_single(self.build_ct_message())

    def send_on_init(self, force=False):
        """
        Send messages in the exact order of your captured dump:
        TP/TA, PI, PTY, MS, CT (0x19), RT, PS, then a blank-PS terminator.
        """
        self.send_tp_ta(force)
        self.send_pi(force)
        self.send_pty(force)
        self.send_ms(force)
        self.send_ct(force)
        self.send_rt(force)
        self.send_ps(force)
        if self.af:
            self.send_af(force)
        # Blank PS terminator
        prev = self.ps
        self.ps = ""
        self.send_ps(force=True)
        self.ps = prev

    # Convenience: original send_all order
    def send_all(self, force=False):
        for fn in (
            self.send_di,
            self.send_tp_ta,
            self.send_pi,
            self.send_pty,
            self.send_ms,
            self.send_rt,
            self.send_ps,
            self.send_af,
        ):
            fn(force)
