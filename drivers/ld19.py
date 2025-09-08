#!/usr/bin/env python3
# ld19_reader.py
"""
LD-19 / LD-06 directional distance reader (Multi-Threaded)
----------------------------------------------------------
• A background thread reads from the serial port at max speed.
• The main thread can call get_scan() to instantly get the latest data
  without blocking or worrying about stale information.
"""
import time
import struct
import threading
from typing import List, Optional

import serial


class LD19:
    # ─── protocol constants ────────────────────────────────────────────────
    _HEADER = b"\x54\x2C"
    _FRAME_LEN = 47
    _PTS = 12

    def __init__(
            self,
            port: str = "/dev/ttyAMA0",
            baud: int = 230_400,
            angles: List[float] | None = None,
            resolution: float = 2.5,  # ± °
            offset: float = -90.0,  # mount orientation offset (degrees)
            dist_max: int = 12,
    ):
        """
        angles      : list of angles (deg) CW from robot front.
        resolution  : tolerance window around each target, degrees.
        offset      : angular offset to account for mounting orientation (deg).
        dist_max    : maximum distance to report, in meters.
        """
        if angles is None:
            angles = [
                135,
                125,
                115,
                105,
                95,
                85,
                75,
                65,
                55,
                45,
                35,
                25,
                15,
                5,
                -5,
                -15,
                -25,
                -35,
                -45,
                -55,
                -65,
                -75,
                -85,
                -95,
                -105,
                -115,
                -125,
                -135,
            ]

        self.targets = [(t + 360) % 360 for t in angles]
        self.w = resolution
        self.offset = offset
        self.max_dist = dist_max

        self._latest: List[Optional[float]] = [None] * len(self.targets)
        self._ser = serial.Serial(port, baud, timeout=0.1)

        # ─── threading setup ───────────────────────────────────────────────
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

        print(f"[LD19] Initialized")

    # ────────────────────────────────────────────────────────────────────────
    # private helpers
    # ────────────────────────────────────────────────────────────────────────
    def _read_loop(self):
        """Runs in a background thread: reads, parses, updates _latest."""
        buf = bytearray()
        while not self._stop_event.is_set():
            try:
                # read chunk (timeout prevents dead-block)
                data = self._ser.read(512)
                if not data:
                    continue
                buf.extend(data)

                while len(buf) >= self._FRAME_LEN:
                    if buf[:2] == self._HEADER:
                        frame = bytes(buf[: self._FRAME_LEN])
                        del buf[: self._FRAME_LEN]

                        frame_updates: dict[int, float] = {}
                        for ang, dist in self._parse_frame(frame):
                            if dist > 0.01:  # ignore zero / invalid
                                idx = self._bucket_index(ang)
                                if idx is not None:
                                    frame_updates[idx] = dist

                        if frame_updates:
                            with self._lock:
                                for idx, dist in frame_updates.items():
                                    self._latest[idx] = dist
                    else:
                        buf.pop(0)  # resync to next header

            except serial.SerialException:
                print("[LD19] Serial disconnected. Attempting reconnect...")
                self._reopen_serial()
            except Exception as e:
                print(f"[LD19] Unhandled read error: {e}")
                time.sleep(1)

    def _reopen_serial(self):
        """Attempt to close & reopen the serial port until success or stop."""
        try:
            self._ser.close()
        except Exception:
            pass
        while not self._stop_event.is_set():
            try:
                self._ser.open()
                print("[LD19] serial reconnected.")
                return
            except Exception:
                time.sleep(1)

    def _parse_frame(self, fr: bytes):
        """Yield (angle°, dist_m) for the 12 samples in one frame."""
        s = struct.unpack_from("<H", fr, 4)[0]
        e = struct.unpack_from("<H", fr, 42)[0]
        span = (e - s + 36000) % 36000
        step = span / (self._PTS - 1) if self._PTS > 1 else 0

        for i in range(self._PTS):
            dist_m = struct.unpack_from("<H", fr, 6 + i * 3)[0] / 1000.0
            dist = min(dist_m, self.max_dist)
            ang = ((s + i * step) / 100.0) % 360.0
            yield ang, dist

    def _bucket_index(self, physical_angle: float) -> Optional[int]:
        """Map physical angle to nearest target bucket index (or None)."""
        logical_angle = (physical_angle + self.offset) % 360.0
        best, idx = self.w + 1, None
        for i, tgt in enumerate(self.targets):
            diff = abs(logical_angle - tgt)
            diff = 360 - diff if diff > 180 else diff
            if diff <= self.w and diff < best:
                best, idx = diff, i
                if diff == 0:  # perfect match → no need to keep searching
                    break
        return idx

    # ────────────────────────────────────────────────────────────────────────
    # public API
    # ────────────────────────────────────────────────────────────────────────
    def get_scan(self) -> List[Optional[float]]:
        """Return the most recent scan (shallow-copied, non-blocking)."""
        with self._lock:
            return self._latest[:]

    def get_recip_scan(self, epsilon: float = 0.1) -> List[float]:
        with self._lock:
            return [
                1.0 / (epsilon + (d if d is not None else self.max_dist))
                for d in self._latest
            ]

    def get_targets(self) -> List[float]:
        """Return a copy of the configured target angles."""
        return self.targets[:]

    def close(self):
        """Stop thread and close serial port."""
        print("[LD19] Stopping thread...")
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        self._ser.close()
        print("[LD19] Thread stopped and port closed.")


# ─── CLI test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ld = None
    try:
        ld = LD19()
        print("Reading from LiDAR. Press Ctrl-C to exit.")
        print("Waiting for initial full scan...")
        while None in ld.get_scan():
            time.sleep(0.05)
        print("Initial scan complete. Streaming data...")

        while True:
            scan = ld.get_scan()
            scan_str = " | ".join(f"{d:4.2f}m" if d is not None else "----" for d in scan)
            print(f"\rScan: [ {scan_str} ]", end="", flush=True)
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nClosing LiDAR.")
    finally:
        if ld:
            ld.close()
