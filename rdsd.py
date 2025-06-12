#!/usr/bin/env python3
import yaml
import time
import logging
import argparse
import sys
import threading
import signal
import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

from uecprds import UECPRDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

@dataclass
class Config:
    serial_port: str
    baudrate: int
    delay_seconds: float
    pi_code: int
    pty_code: int
    music_flag: bool
    tp_flag: bool
    ta_flag: bool
    di_stereo: bool
    di_artificial_head: bool
    di_compressed: bool
    di_dynamic_pty: bool
    ps_texts: List[str]
    ps_center: bool
    ps_scroll_enabled: bool
    ps_scroll_bidirectional: bool
    ps_scroll_speed_seconds: float
    ps_display_delay_seconds: float
    rt_messages: List[str]
    rt_file: Optional[str]
    rt_center: bool
    rt_change_interval_seconds: float
    clock_enable: bool
    clock_interval_seconds: float
    af_enable: bool
    alternate_frequencies: List[float]

    @staticmethod
    def from_yaml(path: str):
        with open(path, "r") as f:
            raw = yaml.safe_load(f)
        return Config(
            serial_port=raw["serial"]["port"],
            baudrate=raw["serial"]["baudrate"],
            delay_seconds=raw["serial"]["delay_seconds"],
            pi_code=raw["station"]["program_identification_code"],
            pty_code=raw["station"]["program_type_code"],
            music_flag=raw["station"]["rds_music_flag"],
            tp_flag=raw["station"]["tp"],
            ta_flag=raw["station"]["ta"],
            di_stereo=raw["flags"]["di"]["stereo"],
            di_artificial_head=raw["flags"]["di"]["artificial_head"],
            di_compressed=raw["flags"]["di"]["compressed"],
            di_dynamic_pty=raw["flags"]["di"]["dynamic_pty"],
            ps_texts=raw["display"]["ps"]["texts"],
            ps_center=raw["display"]["ps"]["center"],
            ps_scroll_enabled=raw["display"]["ps"]["scroll_enabled"],
            ps_scroll_bidirectional=raw["display"]["ps"]["scroll_bidirectional"],
            ps_scroll_speed_seconds=raw["display"]["ps"]["scroll_speed_seconds"],
            ps_display_delay_seconds=raw["display"]["ps"]["display_delay_seconds"],
            rt_messages=raw["display"]["rt"]["messages"],
            rt_file=raw["display"]["rt"].get("file"),
            rt_center=raw["display"]["rt"]["center"],
            rt_change_interval_seconds=raw["display"]["rt"]["change_interval_seconds"],
            clock_enable=raw["clock"]["enable"],
            clock_interval_seconds=raw["clock"]["interval_seconds"],
            af_enable=raw["af"]["enable"],
            alternate_frequencies=raw["af"]["alternate_frequencies"]
        )

    def summary(self):
        di_flags = (
            f"S={int(self.di_stereo)}, AH={int(self.di_artificial_head)}, "
            f"C={int(self.di_compressed)}, DP={int(self.di_dynamic_pty)}"
        )
        return (
            f"Serial: {self.serial_port} @ {self.baudrate} bps\n"
            f"PI: 0x{self.pi_code:04X}, PTY: {self.pty_code}, MS: {self.music_flag}\n"
            f"TP: {self.tp_flag}, TA: {self.ta_flag}, DI: {di_flags}\n"
            f"PS entries: {len(self.ps_texts)}, RT entries: {len(self.rt_messages)}\n"
            f"AF enabled: {self.af_enable} ({len(self.alternate_frequencies)} entries)\n"
            f"Clock enabled: {self.clock_enable} (interval {self.clock_interval_seconds}s)"
        )


class RDSDaemon:
    def __init__(self, config: Config, debug=False):
        self.config = config
        self.debug = debug
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.rds = self._init_uecprds()
        self.scroll_frames = self._generate_ps_scroll()

    def _init_uecprds(self):
        di = (
            (int(self.config.di_stereo) << 0)
            | (int(self.config.di_artificial_head) << 1)
            | (int(self.config.di_compressed) << 2)
            | (int(self.config.di_dynamic_pty) << 3)
        )
        rds = UECPRDS(
            port=self.config.serial_port,
            baudrate=self.config.baudrate,
            delay=self.config.delay_seconds,
            pi=self.config.pi_code,
            pty=self.config.pty_code,
            ms=self.config.music_flag,
            tp=self.config.tp_flag,
            ta=self.config.ta_flag,
            di=di,
            debug=self.debug
        )
        rds.send_static_init()
        logging.info(f"TP={self.config.tp_flag}, TA={self.config.ta_flag}, DI=0x{di:02X}")

        if self.config.af_enable:
            rds.send_af(self.config.alternate_frequencies)
            logging.info(f"AF frequencies sent: {self.config.alternate_frequencies}")

        return rds

    def _generate_ps_scroll(self):
        names = self.config.ps_texts
        text = " ".join(names).strip().replace("  ", " ")
        width = 8
        if not self.config.ps_scroll_enabled or len(text) <= width:
            return []
        frames = []
        if not self.config.ps_scroll_bidirectional:
            data = text + " " + text[:width - 1]
            frames = [data[i:i + width] for i in range(len(data) - width + 1)]
        else:
            for i in range(len(text) - width + 1):
                frames.append(text[i:i + width])
            for i in range(len(text) - width - 1, 0, -1):
                frames.append(text[i:i + width])
        return frames

    def _safe_send_ps(self, text):
        with self.lock:
            self.rds.send_ps(text)
            logging.info(f"Sent PS: {text}")

    def _safe_send_rt(self, text):
        with self.lock:
            self.rds.send_rt(text)
            logging.info(f"Sent RT: {text}")

    def _ps_worker(self):
        idx = 0
        while not self.stop_event.is_set():
            if self.scroll_frames:
                frame = self.scroll_frames[idx % len(self.scroll_frames)]
                idx += 1
                text = frame.center(8) if self.config.ps_center else frame.ljust(8)
                self._safe_send_ps(text)
                self.stop_event.wait(self.config.ps_scroll_speed_seconds)
            else:
                for ps in self.config.ps_texts:
                    text = ps.center(8) if self.config.ps_center else ps.ljust(8)
                    self._safe_send_ps(text)
                    self.stop_event.wait(self.config.ps_display_delay_seconds)

    def _rt_worker(self):
        idx = 0
        while not self.stop_event.is_set():
            current_rt_text = ""
            # Check if rt_file is specified in config and if the file actually exists
            if self.config.rt_file and Path(self.config.rt_file).is_file():
                try:
                    current_rt_text = Path(self.config.rt_file).read_text().strip()
                    # If file is empty, fallback to first message to avoid sending empty RT
                    if not current_rt_text and self.config.rt_messages:
                        current_rt_text = self.config.rt_messages[0]
                except Exception as e:
                    logging.warning(f"Error reading RT file '{self.config.rt_file}': {e}. Falling back to default message.")
                    if self.config.rt_messages:
                        current_rt_text = self.config.rt_messages[0]
                    else:
                        current_rt_text = "NO RT FILE OR MESSAGES" # Fallback if neither is available
            else: # rt_file is not specified, or the specified file does not exist
                if self.config.rt_messages:
                    current_rt_text = self.config.rt_messages[idx % len(self.config.rt_messages)]
                    idx += 1 # Increment only when rotating through the list
                else:
                    current_rt_text = "NO RT MESSAGES CONFIGURED" # Fallback if no messages are configured

            # Ensure RT text is not empty before sending
            if not current_rt_text:
                 current_rt_text = "RADIO TEXT" # Default safe string if everything else fails

            text_to_send = current_rt_text.center(64) if self.config.rt_center else current_rt_text.ljust(64)
            self._safe_send_rt(text_to_send)
            self.stop_event.wait(self.config.rt_change_interval_seconds)
            
    def _ct_worker(self):
        while not self.stop_event.is_set():
            now = datetime.datetime.now()
            with self.lock:
                self.rds.send_ct_profline(now)
                logging.info("Sent Profline CT")
            self.stop_event.wait(self.config.clock_interval_seconds)

    def run(self):
        threads = [
            threading.Thread(target=self._ps_worker, name="PS-Thread"),
            threading.Thread(target=self._rt_worker, name="RT-Thread")
        ]
        if self.config.clock_enable:
            threads.append(threading.Thread(target=self._ct_worker, name="CT-Thread"))
        for t in threads: t.start()
        try:
            while not self.stop_event.is_set():
                self.stop_event.wait(0.5)
        except KeyboardInterrupt:
            logging.info("Interrupted, shutting down...")
        finally:
            self.stop_event.set()
            for t in threads: t.join()
            logging.info("Daemon exited.")

def main():
    parser = argparse.ArgumentParser(description="RDS Daemon")
    parser.add_argument("--cfg", required=True, help="YAML config file")
    parser.add_argument("--debug", action="store_true", help="Enable UECP hex debug output")
    args = parser.parse_args()
    try:
        cfg = Config.from_yaml(args.cfg)
        logging.info("Config loaded successfully.")
        logging.info("\n" + cfg.summary())
        daemon = RDSDaemon(cfg, debug=args.debug)
        signal.signal(signal.SIGINT, lambda *_: daemon.stop_event.set())
        signal.signal(signal.SIGTERM, lambda *_: daemon.stop_event.set())
        daemon.run()
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
