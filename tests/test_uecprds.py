import unittest
import datetime
from uecprds import UECPRDS

class TestUECPRDS(unittest.TestCase):
    def setUp(self):
        self.u = UECPRDS('', 9600, 0, 0x1337, 15, True, True, False, 0x00)

    def hex(self, b: bytes) -> str:
        return b.hex()

    def test_build_frame_ps(self):
        group = self.u.build_group(0x02, b'DEMO    ')
        frame = self.u.build_frame(group)
        self.assertEqual(self.hex(frame), 'fe0000000b02000044454d4f202020209180ff')

    def test_build_frame_tp(self):
        group = self.u.build_group(0x03, bytes([0x02]))
        frame = self.u.build_frame(group)
        self.assertEqual(self.hex(frame), 'fe0000000403000002fc59ff')

    def test_build_frame_pi(self):
        group = self.u.build_group(0x01, bytes([0x13, 0x37]))
        frame = self.u.build_frame(group)
        self.assertEqual(self.hex(frame), 'fe0000000501000013371e49ff')

    def test_build_frame_pty(self):
        group = self.u.build_group(0x07, bytes([0x0f]))
        frame = self.u.build_frame(group)
        self.assertEqual(self.hex(frame), 'fe000000040700000fe705ff')

    def test_build_frame_ms(self):
        group = self.u.build_group(0x05, bytes([0x01]))
        frame = self.u.build_frame(group)
        self.assertEqual(self.hex(frame), 'fe0000000405000001eba3ff')

    def test_build_frame_di(self):
        group = self.u.build_group(0x04, bytes([0x00]))
        frame = self.u.build_frame(group)
        self.assertEqual(self.hex(frame), 'fe00000004040000008d36ff')

    def test_build_frame_af(self):
        payload = self.u.build_af_payload([92.4])
        self.assertIsNotNone(payload)
        group = self.u.build_group(0x13, payload)
        frame = self.u.build_frame(group)
        self.assertEqual(self.hex(frame), 'fe0000000a130000050000e1310060643bff')

    def test_build_frame_ct_profline(self):
        t = datetime.datetime(2023, 8, 25, 12, 34, 56)
        payload = bytes([t.year % 100, t.month, t.day, t.hour, t.minute, t.second, 0x00, 0x00])
        group = self.u.build_group(0x0D19, payload)
        frame = self.u.build_frame(group)
        self.assertEqual(self.hex(frame), 'fe0000000b0d19001708190c22380000337dff')

if __name__ == '__main__':
    unittest.main()
