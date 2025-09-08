# camera_pi.py
import time, threading
from PIL import Image
from picamera2 import Picamera2


class Camera:
    def __init__(self, resolution=(640, 480), fps=5):
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

        self.cam = Picamera2()
        self.cam.configure(
            self.cam.create_still_configuration(
                main={"size": resolution},
                controls={"FrameRate": fps}
            )
        )
        self.cam.start()
        time.sleep(2)  # warm-up to match capture script

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                arr = self.cam.capture_array()
                with self._lock:
                    self._frame = Image.fromarray(arr)
            except Exception as e:
                print(f"[PiCameraDriver] Capture error: {e}")
                time.sleep(0.1)

    def get_frame(self):
        with self._lock:
            return self._frame.copy() if self._frame else None

    def shutdown(self):
        self._stop.set()
        self._thread.join()
        if self.cam.started:
            self.cam.stop()
