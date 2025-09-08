#!/usr/bin/env python3
# controller.py – one-file orchestration

import signal, sys, time, threading
from queue import Queue, Empty, Full  # ← added Full
import gpiod

# ─── local modules ───────────────────────────────────────────────────
from systems.state import SharedState
from systems.inference import Inference
from systems.vpr import VPRSystem
from systems.recognizer import ImageRecognizer

from drivers.pwmcontroller import PWMController
from drivers.ld19 import LD19
from drivers.bno085 import BNO085
from drivers.picam import Camera

MODEL_PATH = "agents/hobbs_v10_recip.pt"


class Controller:
    def __init__(self):
        # ── shared state & queues ────────────────────────────────────
        self.state = SharedState()
        self.obs_q = Queue(maxsize=1)
        self.act_q = Queue(maxsize=1)
        self.rec_q = Queue(maxsize=2)
        self.stop_ev = threading.Event()

        # ── hardware drivers ─────────────────────────────────────────
        self.pwm = PWMController()
        self.lidar = LD19()
        self.imu = BNO085()
        self.camera = Camera()

        # ── subsystems ───────────────────────────────────────────────
        self.recognizer = ImageRecognizer(self.state, self.rec_q)
        self.recognizer.start()

        self.vpr = VPRSystem(self.state)
        self.vpr.start()

        # ── worker threads ───────────────────────────────────────────
        self.t_sensor = threading.Thread(target=self._sensor_loop, daemon=True)
        self.t_act = threading.Thread(target=self._act_loop, daemon=True)
        self.t_sensor.start()
        self.t_act.start()

        self.t_vpr = None
        self._vpr_loop_ev = threading.Event()
        self.t_btn = None  # button watcher (started below)

        self.inf = None
        self.stop_region = None
        self.stop_threshold = 0.75

        # ── GPIO setup ───────────────────────────────────────────────
        try:
            chip = gpiod.Chip("gpiochip0")
        except OSError:
            chip = gpiod.find_line("GPIO23").chip

        # Button on GPIO-22  (triggers recognizer)
        self._btn_line = chip.get_line(22)
        self._btn_line.request(
            consumer="recognizer-trigger",
            type=gpiod.LINE_REQ_DIR_IN,
            flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP
        )

        # Drive-enable switch on GPIO-23
        self._drv_line = chip.get_line(23)
        self._drv_line.request(
            consumer="auto-nav-drive-enable",
            type=gpiod.LINE_REQ_DIR_IN,
            flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP,
        )

        self._drive_enable_counter = 0
        self._drive_enable_threshold = 5  # tweakable

        # start button-watch thread
        self.t_btn = threading.Thread(target=self._btn_loop, daemon=True)
        self.t_btn.start()

    def drive_enabled(self):
        val = self._drv_line.get_value()
        self._drive_enable_counter = (
            self._drive_enable_counter + 1 if val == 1 else 0
        )
        return self._drive_enable_counter > self._drive_enable_threshold

    # ─────────────────────────────────────────────────────────────────
    # Vision place-recognition image feeder
    def _vpr_loop(self):
        while not self._vpr_loop_ev.is_set():
            try:
                img = self.camera.get_frame()
                if img:
                    self.vpr.set_image(img)
            except Exception as e:
                print(f"[VPR Feed] {e}")
            time.sleep(0.01)

    def _start_vpr_loop(self):
        if self.t_vpr and self.t_vpr.is_alive():
            return
        self._vpr_loop_ev.clear()
        self.t_vpr = threading.Thread(target=self._vpr_loop, daemon=True)
        self.t_vpr.start()
        print("[VPR] Feed loop started.")

    def _stop_vpr_loop(self):
        if self.t_vpr and self.t_vpr.is_alive():
            self._vpr_loop_ev.set()
            self.t_vpr.join(timeout=0.2)
            print("[VPR] Feed loop stopped.")

    # ─────────────────────────────────────────────────────────────────
    def set_stop_region(self, region: str | None):
        print("NEW STOP REGION:", region)
        self.stop_region = region
        if region:
            self._start_vpr_loop()
        else:
            self.vpr.clear()
            self._stop_vpr_loop()

    # ─────────────────────────────────────────────────────────────────
    # Sensor producer → obs_q
    def _sensor_loop(self):
        while not self.stop_ev.is_set():
            sin_y, cos_y = self.imu.yaw()
            obs = {
                "lidar": self.lidar.get_recip_scan(),
                "accel_x": self.imu.accel_x,
                "gyro_z": self.imu.gyro_z,
                "sin_yaw": sin_y,
                "cos_yaw": cos_y,
            }
            try:
                self.obs_q.put_nowait(obs)
            except Full:
                pass
            except Empty:
                pass
            time.sleep(0.01)

    # ─────────────────────────────────────────────────────────────────
    # Actuator consumer ← act_q
    def _act_loop(self):
        while not self.stop_ev.is_set():
            try:
                top_regions = self.vpr.get_top_regions()
                if (self.stop_region and
                        any(r == self.stop_region and c > self.stop_threshold
                            for r, c in top_regions)):
                    self.pwm.hard_brake()
                    try:
                        self.act_q.get_nowait()
                    except Empty:
                        pass
                else:
                    if self.drive_enabled():
                        throttle, steer = self.act_q.get(timeout=0.1)
                        self.pwm.set_controls(throttle, steer)
                    else:
                        self.pwm.set_controls(0, 0)
            except Empty:
                continue
            except Exception as e:
                print(f"[Actuator] {e}")

    # ─────────────────────────────────────────────────────────────────
    # Button watcher → rec_q
    def _btn_loop(self):
        prev = 1
        while not self.stop_ev.is_set():
            val = self._btn_line.get_value()
            if val == 0 and prev == 1:  # falling edge = press
                print("BUTTON PRESSED GETTING OBSERVATION")
                frame = self.camera.get_frame()
                if frame:
                    try:
                        self.rec_q.put_nowait(frame)
                    except Full:
                        pass
            prev = val
            time.sleep(0.05)

    # ─────────────────────────────────────────────────────────────────
    def start_inference(self, model_path):
        if self.inf and self.inf.is_running:
            return
        self.inf = Inference(self.state, self.obs_q, self.act_q)
        self.inf.load_model(model_path)
        self.inf.start()
        print("► Inference started.")

    def stop_inference(self):
        if self.inf:
            self.inf.shutdown()
            self.inf.join()
            self.pwm.hard_brake()
            self.pwm.set_controls(0, 0)
            print("■ Inference stopped.")

    # ─────────────────────────────────────────────────────────────────
    def get_status(self):
        return self.state.snapshot()

    # ─────────────────────────────────────────────────────────────────
    def shutdown_all(self):
        if self.stop_ev.is_set():
            return
        self.stop_ev.set()

        self.stop_inference()

        try:
            self.t_act.join(timeout=0.2)
        except Exception:
            pass
        self._stop_vpr_loop()

        # stop recognizer & button thread
        self.recognizer.shutdown()
        try:
            self.t_btn.join(timeout=0.2)
        except Exception:
            pass

        # hardware cleanup
        self.pwm.cleanup()
        self.lidar.close()
        self.imu.shutdown()
        self.camera.shutdown()
        self.vpr.shutdown()

        try:
            self._drv_line.release()
            self._btn_line.release()
        except Exception:
            pass

        print("✅ Clean shutdown complete.")


# ─────────────────────────────────────────────────────────────────────
def _run_cli():
    ctl = Controller()

    def _sig(*_):
        ctl.pwm.hard_brake()
        ctl.shutdown_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    ctl.start_inference(MODEL_PATH)
    print("Controller running. Ctrl-C to stop.")
    while True:
        print(ctl.vpr.get_top_regions())


if __name__ == "__main__":
    _run_cli()
