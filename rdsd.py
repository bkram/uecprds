#!/usr/bin/env python3
"""
RDS Daemon (rdsd):
- Periodically sends RDS Radiotext and Program Service (PS) data over serial.
- Uses a class-based design with threading for reliable, non-blocking updates.
- Supports graceful shutdown via SIGINT/SIGTERM.

Configuration:
- Loaded from YAML via `Config.from_yaml(path)`.
- All RDS parameters (PI, PTY, MS, TP, TA, DI flags) are configurable.
- Text lists or file overrides for Radiotext with immediate update on file change.
- PS scrolling or fixed-name cycling.

Usage:
    python3 rdsd.py --cfg /path/to/config.yml
"""

import yaml
import time
import logging
import argparse
import sys
import threading
import signal
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

# Attempt to import UECPRDS
try:
    from uecprds import UECPRDS
except ImportError:
    print("Error: The 'uecprds' library is not installed.", file=sys.stderr)
    print("Install via: pip install uecprds-rds", file=sys.stderr)
    sys.exit(1)

# Configure logging to include thread names
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(threadName)s - %(levelname)s - %(message)s",
)


@dataclass
class Config:
    """
    Configuration for the RDS Daemon, loaded from a YAML file.
    """

    serial_port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    lib_delay: float = 1.0
    pi_code: int = 0x0000
    pty_code: int = 0
    music_flag: bool = True
    tp_flag: bool = False
    ta_flag: bool = False
    di_stereo: bool = False
    di_artificial_head: bool = False
    di_compressed: bool = False
    di_dynamic_pty: bool = False
    program_service_names: List[str] = field(default_factory=lambda: ["DEFAULT"])
    radiotext_messages: List[str] = field(default_factory=lambda: ["RADIOTEXT"])
    radiotext_file: Optional[Path] = None
    center_ps: bool = False
    center_rt: bool = False
    ps_scroll_enabled: bool = False
    ps_scroll_bidirectional: bool = False
    rt_change_interval: float = 10.0
    ps_scroll_speed: float = 0.5
    ps_display_delay: float = 2.0

    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        """
        Load and parse a YAML configuration file into a Config instance.
        """
        if not path.is_file():
            raise FileNotFoundError(f"Config file not found: {path}")
        data = yaml.safe_load(path.read_text()) or {}
        default = cls()
        di = data.get("rds_di", {}) or {}
        return cls(
            serial_port=data.get("serial_port", default.serial_port),
            baudrate=data.get("baudrate", default.baudrate),
            lib_delay=data.get("lib_delay", default.lib_delay),
            pi_code=data.get("program_identification_code", default.pi_code),
            pty_code=data.get("program_type_code", default.pty_code),
            music_flag=data.get("rds_music_flag", default.music_flag),
            tp_flag=data.get("tp", default.tp_flag),
            ta_flag=data.get("ta", default.ta_flag),
            di_stereo=di.get("stereo", default.di_stereo),
            di_artificial_head=di.get("artificial_head", default.di_artificial_head),
            di_compressed=di.get("compressed", default.di_compressed),
            di_dynamic_pty=di.get("dynamic_pty", default.di_dynamic_pty),
            program_service_names=data.get(
                "program_service_names", default.program_service_names
            ),
            radiotext_messages=data.get(
                "radiotext_messages", default.radiotext_messages
            ),
            radiotext_file=Path(data["radiotext_file"])
            if data.get("radiotext_file")
            else default.radiotext_file,
            center_ps=data.get("center_ps_display", default.center_ps),
            center_rt=data.get("center_radiotext_display", default.center_rt),
            ps_scroll_enabled=data.get("ps_scroll_enabled", default.ps_scroll_enabled),
            ps_scroll_bidirectional=data.get(
                "ps_scroll_bidirectional", default.ps_scroll_bidirectional
            ),
            rt_change_interval=data.get(
                "radiotext_change_interval_seconds", default.rt_change_interval
            ),
            ps_scroll_speed=data.get(
                "ps_scroll_speed_seconds", default.ps_scroll_speed
            ),
            ps_display_delay=data.get(
                "ps_display_delay_seconds", default.ps_display_delay
            ),
        )


class RDSDaemon:
    """
    Manages RDS transmission threads and interaction with UECPRDS.
    """

    def __init__(self, config: Config):
        self.config = config
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.rds = self._initialize_rds()
        self.scroll_frames = self._generate_scroll_frames()

    def _initialize_rds(self) -> UECPRDS:
        rds = UECPRDS(
            port=self.config.serial_port,
            baudrate=self.config.baudrate,
            delay=self.config.lib_delay,
            pi=self.config.pi_code,
            pty=self.config.pty_code,
            ms=self.config.music_flag,
            tp=self.config.tp_flag,
            ta=self.config.ta_flag,
        )
        di = (
            (int(self.config.di_stereo) << 0)
            | (int(self.config.di_artificial_head) << 1)
            | (int(self.config.di_compressed) << 2)
            | (int(self.config.di_dynamic_pty) << 3)
        )
        rds.set_di(di)
        rds.send_di()
        logging.info(f"DI byte set to 0x{di:02X}")
        logging.info(f"TP={self.config.tp_flag}, TA={self.config.ta_flag}")
        return rds

    def _generate_scroll_frames(self) -> List[str]:
        names = self.config.program_service_names or []
        text = " ".join(names).strip()
        text = " ".join(text.split())
        width = 8
        if not self.config.ps_scroll_enabled or len(text) <= width:
            return []
        frames = []
        if not self.config.ps_scroll_bidirectional:
            data = text + " " + text[: width - 1]
            frames = [data[i : i + width] for i in range(len(data) - width + 1)]
        else:
            for i in range(len(text) - width + 1):
                frames.append(text[i : i + width])
            for i in range(len(text) - width - 1, 0, -1):
                frames.append(text[i : i + width])
        return [f for i, f in enumerate(frames) if i == 0 or f != frames[i - 1]]

    def _safe_send(self, kind: str, msg: str):
        with self.lock:
            if self.stop_event.is_set():
                return
            if kind == "ps":
                self.rds.set_ps(msg)
                self.rds.send_ps()
            else:
                self.rds.set_rt(msg)
                self.rds.send_rt()
            logging.info(f"Sent {kind.upper()}: {msg}")

    def _rt_worker(self):
        """
        Worker thread to send radiotext immediately then on changes or interval:
        - Sends initial RT from file or list.
        - Monitors file for modifications and updates immediately.
        - Cycles list entries every `rt_change_interval` if no file.
        """
        idx = 0
        last_list_ts = time.time()
        last_mtime = None
        # Initial send
        text = None
        if self.config.radiotext_file and self.config.radiotext_file.is_file():
            stat = self.config.radiotext_file.stat()
            last_mtime = stat.st_mtime
            text = self.config.radiotext_file.read_text().strip()
        else:
            msgs = self.config.radiotext_messages or []
            if msgs:
                text = msgs[idx % len(msgs)]
                idx += 1
                last_list_ts = time.time()
        if text:
            payload = text.center(64) if self.config.center_rt else text.ljust(64)
            self._safe_send("rt", payload)
        # Poll loop
        while not self.stop_event.is_set():
            # File monitoring
            if self.config.radiotext_file and self.config.radiotext_file.is_file():
                try:
                    stat = self.config.radiotext_file.stat()
                    if last_mtime is None or stat.st_mtime > last_mtime:
                        last_mtime = stat.st_mtime
                        text = self.config.radiotext_file.read_text().strip()
                        payload = (
                            text.center(64) if self.config.center_rt else text.ljust(64)
                        )
                        self._safe_send("rt", payload)
                        last_list_ts = time.time()
                except Exception as e:
                    logging.error(f"Error reading RT file: {e}")
            else:
                # List cycling
                if time.time() - last_list_ts >= self.config.rt_change_interval:
                    msgs = self.config.radiotext_messages or []
                    if msgs:
                        text = msgs[idx % len(msgs)]
                        idx += 1
                        last_list_ts = time.time()
                        payload = (
                            text.center(64) if self.config.center_rt else text.ljust(64)
                        )
                        self._safe_send("rt", payload)
            time.sleep(1)

    def _ps_worker(self):
        idx = 0
        while not self.stop_event.is_set():
            if self.scroll_frames:
                frame = self.scroll_frames[idx % len(self.scroll_frames)]
                idx += 1
                payload = frame.center(8) if self.config.center_ps else frame.ljust(8)
                self._safe_send("ps", payload)
                time.sleep(self.config.ps_scroll_speed)
            else:
                names = self.config.program_service_names or []
                if not names:
                    time.sleep(1)
                    continue
                name = names[idx % len(names)]
                idx += 1
                payload = name.center(8) if self.config.center_ps else name.ljust(8)
                self._safe_send("ps", payload)
                delay = self.config.ps_display_delay if len(names) > 1 else 60
                time.sleep(delay)

    def run(self):
        threads = [
            threading.Thread(target=self._rt_worker, name="RT-Thread"),
            threading.Thread(target=self._ps_worker, name="PS-Thread"),
        ]
        for t in threads:
            t.start()
        try:
            while not self.stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            logging.info("KeyboardInterrupt, stopping...")
        finally:
            self.stop_event.set()
            for t in threads:
                t.join()
            logging.info("Daemon exited.")

    def stop(self):
        """
        Signal the daemon to stop.
        """
        self.stop_event.set()


def main():
    parser = argparse.ArgumentParser(description="RDS Daemon (rdsd)")
    parser.add_argument("--cfg", type=Path, required=True, help="YAML config path")
    args = parser.parse_args()
    try:
        cfg = Config.from_yaml(args.cfg)
        daemon = RDSDaemon(cfg)
        signal.signal(signal.SIGINT, lambda s, f: daemon.stop())
        signal.signal(signal.SIGTERM, lambda s, f: daemon.stop())
        daemon.run()
    except Exception as e:
        logging.error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
