import serial
import time
import datetime

class UECPRDS:
    """
    Profline-compliant UECPRDS encoder (strict initialization ordering)
    """

    def __init__(self, port, baudrate, delay, pi, pty, ms, tp, ta, di, debug=False):
        self.port = port
        self.baudrate = baudrate
        self.delay = delay
        self.pi = pi
        self.pty = pty
        self.ms = ms
        self.tp = tp
        self.ta = ta
        self.di = di
        self.debug = debug

    # --- Main public entry point for startup ---
    def send_static_init(self):
        self.send_tp_ta()
        self.send_pi()
        self.send_pty()
        self.send_ms()
        self.send_di()

    def send_af(self, af_list):
        payload = self.build_af_payload(af_list)
        self.send_message(self.build_group(0x13, payload))

    def send_ps(self, text):
        ps = text[:8].ljust(8)
        self.send_message(self.build_group(0x02, ps.encode("ascii", "replace")))

    def send_rt(self, text):
        rt_data = text.encode("latin-1", "replace")[:64].ljust(64, b" ")
        payload = b"\x41\x00" + rt_data
        self.send_message(self.build_group(0x0A, payload))

    def send_ct_profline(self, dt: datetime.datetime):
        payload = bytearray([
            dt.year % 100,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second,
            0x00, 0x00
        ])
        self.send_message(self.build_group(0x0D19, payload))

    # --- Group builders ---
    def send_tp_ta(self):
        val = ((1 if self.tp else 0) << 1) | (1 if self.ta else 0)
        self.send_message(self.build_group(0x03, bytes([val])))

    def send_pi(self):
        self.send_message(self.build_group(0x01, self.pi.to_bytes(2, "big")))

    def send_pty(self):
        self.send_message(self.build_group(0x07, bytes([self.pty])))

    def send_ms(self):
        self.send_message(self.build_group(0x05, bytes([1 if self.ms else 0])))

    def send_di(self):
        self.send_message(self.build_group(0x04, bytes([self.di])))

    # --- AF Logic ---
    def build_af_payload(self, af_list):
        encoded_afs = []
        for f in af_list:
            try:
                encoded_afs.append(self.encode_af(f))
            except Exception as e:
                print(f"[AF ENCODE ERROR] {f} MHz skipped: {e}")

        if len(encoded_afs) == 1:
            return self.build_af_method_05(encoded_afs)
        elif 2 <= len(encoded_afs) <= 3:
            return self.build_af_method_07(encoded_afs)
        elif 4 <= len(encoded_afs) <= 11:
            return self.build_af_method_0f(encoded_afs)
        else:
            print("[WARN] Invalid AF list length")
            return b''

    def encode_af(self, freq_mhz):
        if not (87.6 <= freq_mhz <= 107.9):
            raise ValueError(f"AF {freq_mhz} MHz outside valid range.")
        af_code = int(round((freq_mhz - 87.5) * 10))
        if not (1 <= af_code <= 204):
            raise ValueError(f"AF code {af_code} invalid.")
        return af_code

    def build_af_method_05(self, encoded_afs):
        payload = bytearray([0x05, 0x00, 0x00, 0xE1])
        payload.append(encoded_afs[0])
        payload += b'\x00\x60'
        return payload

    def build_af_method_07(self, encoded_afs):
        payload = bytearray([0x07, 0x00, 0x00])
        payload.append(0xE0 + len(encoded_afs))
        payload.extend(encoded_afs)
        payload.extend([0x00] * (3 - len(encoded_afs)))
        payload += b'\x00\xD3' if len(encoded_afs) == 2 else b'\x00\xEE'
        return payload

    def build_af_method_0f(self, encoded_afs):
        payload = bytearray([0x0F, 0x00, 0x00, 0xEB])
        payload.extend(encoded_afs)
        payload.extend([0x00] * (11 - len(encoded_afs)))
        payload += b'\x00\xAC'
        return payload

    # --- UECP Core Framing ---
    def build_group(self, mec, data):
        if mec > 0xFF:
            header = bytes([(mec >> 8) & 0xFF, mec & 0xFF, 0x00])
        else:
            header = bytes([mec, 0x00, 0x00])
        return header + data

    def send_message(self, msg):
        frame = self.build_frame(msg)
        if self.debug:
            print(f"[UECP HEX] {frame.hex()}")
        with serial.Serial(self.port, self.baudrate, timeout=1) as ser:
            ser.write(frame)
            ser.flush()
            time.sleep(self.delay)

    def build_frame(self, msg):
        header = b'\x00\x00\x00' + bytes([len(msg)])
        payload = header + msg
        crc = self.crc16(payload)
        full = payload + crc.to_bytes(2, 'big')
        stuffed = self.byte_stuff(full)
        return b'\xfe' + stuffed + b'\xff'

    def crc16(self, data, poly=0x1021, init=0xFFFF):
        crc = init
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        return crc ^ 0xFFFF

    def byte_stuff(self, data):
        stuffed = bytearray()
        for b in data:
            stuffed.append(b)
            if b in (0xFE, 0xFF):
                stuffed.append(0xFD)
        return bytes(stuffed)
