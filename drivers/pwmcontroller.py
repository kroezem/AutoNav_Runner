#!/usr/bin/env python3
import time
import torch
import torch.nn as nn
from periphery import PWM

FRAME_NS = 20_000_000  # 50 Hz frame
STEER_MIN, STEER_MAX = 1000, 2000  # μs
THROTTLE_NEUTRAL = 1500  # μs
THROTTLE_BRAKE_US = 1000  # full-reverse / brake
BRAKE_HOLD_S = 2  # seconds to hold on shutdown

THR_DEADBAND = 0.00  # NN output ≤ this → no drive
THR_START_US = 1575  # first pulse that moves wheels
THR_MAX_US = 1600  # cap
THR_RANGE_US = THR_MAX_US - THR_START_US


# ──────────────── helpers ────────────────
def us_to_ns(us: int) -> int:
    """Microseconds → nanoseconds (integer)."""
    return us * 1_000


class PWMController:
    def __init__(self):
        self.esc = PWM(0, 0)  # throttle
        self.servo = PWM(0, 1)  # steering
        self.esc.period_ns = self.servo.period_ns = FRAME_NS
        self.throttle_us = THROTTLE_NEUTRAL
        self.steer_us = 1500
        self.apply_pwm()
        self.esc.enable()
        self.servo.enable()

        self.servo.duty_cycle_ns = us_to_ns(1500)
        # quick ESC arm
        self.esc.duty_cycle_ns = us_to_ns(1000)
        time.sleep(1)
        self.esc.duty_cycle_ns = us_to_ns(THROTTLE_NEUTRAL)
        time.sleep(1)
        print("[PWM] ESC armed")

    # ---------------- motor helpers ----------------
    def apply_pwm(self):
        self.servo.duty_cycle_ns = us_to_ns(self.steer_us)
        self.esc.duty_cycle_ns = us_to_ns(self.throttle_us)

    def set_controls(self, throttle: float, steering: float):
        # throttle mapping
        if throttle <= THR_DEADBAND:
            self.throttle_us = THROTTLE_NEUTRAL
        else:
            val = min(1.0, (throttle - THR_DEADBAND) / (1.0 - THR_DEADBAND))
            self.throttle_us = int(THR_START_US + val * THR_RANGE_US)

        # steering mapping
        self.steer_us = int(1500 + steering * 500)
        self.steer_us = max(STEER_MIN, min(self.steer_us, STEER_MAX))
        self.apply_pwm()

    def hard_brake(self, hold_s: float = 0.0):
        self.throttle_us = THROTTLE_BRAKE_US
        self.apply_pwm()
        if hold_s > 0:
            time.sleep(hold_s)
            self.throttle_us = THROTTLE_NEUTRAL
            self.apply_pwm()

    # ---------------- shutdown ----------------
    def cleanup(self):
        self.hard_brake(BRAKE_HOLD_S)  # full stop before power-down
        self.steer_us = 1500
        self.apply_pwm()
        time.sleep(0.5)
        self.esc.disable()
        self.servo.disable()
        self.esc.close()
        self.servo.close()
        print("[PWM] released")
