import time
import serial
import gpiod
import adafruit_bno08x
from adafruit_bno08x.uart import BNO08X_UART
import math
from scipy.spatial.transform import Rotation as R


class BNO085:
    def __init__(self, uart_path="/dev/ttyAMA2", baudrate=3_000_000, reset_pin=26):
        self.reset_pin = reset_pin
        self.uart_path = uart_path
        self.baudrate = baudrate
        self.bno = None

        self._reset_sensor()
        self._init_uart()
        self._enable_features()

        print(f"[BNO085] Initialized")

    def _reset_sensor(self):
        try:
            chip = gpiod.Chip("gpiochip0")
            line = chip.get_line(self.reset_pin)
            line.request(consumer="bno_rst", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
            time.sleep(0.02)
            line.set_value(1)
            time.sleep(0.06)
        except Exception as e:
            raise RuntimeError(f"[BNO085] Reset failed: {e}")

    def _init_uart(self):
        try:
            uart = serial.Serial(self.uart_path, baudrate=self.baudrate, timeout=0.01)
            self.bno = BNO08X_UART(uart, reset=None, debug=False)
        except Exception as e:
            raise RuntimeError(f"[BNO085] UART init failed: {e}")

    def _enable_features(self):
        try:
            for f in (
                    adafruit_bno08x.BNO_REPORT_ROTATION_VECTOR,
                    adafruit_bno08x.BNO_REPORT_LINEAR_ACCELERATION,
                    adafruit_bno08x.BNO_REPORT_GYROSCOPE,
            ):
                self.bno.enable_feature(f)
            time.sleep(0.1)
        except Exception as e:
            raise RuntimeError(f"[BNO085] Feature enable failed: {e}")

    def shutdown(self):
        try:
            # Attempt to cleanly close UART if possible
            if isinstance(self.bno, BNO08X_UART) and hasattr(self.bno, 'uart'):
                self.bno.uart.close()
            print("[BNO085] Shutdown complete.")
        except Exception as e:
            print(f"[BNO085] Shutdown error: {e}")

    @property
    def gyro_z(self) -> float:
        try:
            _, _, gz = self.bno.gyro
            return gz if gz is not None else 0.0
        except:
            return 0.0

    @property
    def accel_x(self) -> float:
        try:
            ax, _, _ = self.bno.linear_acceleration
            return ax if ax is not None else 0.0
        except:
            return 0.0

    @property
    def quaternion(self) -> tuple:
        try:
            q = self.bno.quaternion
            return q if all(v is not None for v in q) else (0.0, 0.0, 0.0, 1.0)
        except:
            return (0.0, 0.0, 0.0, 1.0)

    def yaw(self) -> tuple[float, float]:
        try:
            qi, qj, qk, qr = self.quaternion
            yaw_rad = R.from_quat([qi, qj, qk, qr]).as_euler('zyx')[0]
            return math.sin(yaw_rad), math.cos(yaw_rad)
        except:
            return 0.0, 1.0


if __name__ == "__main__":
    imu = None
    try:
        print("[BNO085] Initializing...")
        imu = BNO085()
        print("[BNO085] Ready.\n")

        while True:
            ax = imu.accel_x
            gz = imu.gyro_z
            sin_yaw, cos_yaw = imu.yaw()
            print(f"AX: {ax:+.3f}  |  GZ: {gz:+.3f}  |  sin(yaw): {sin_yaw:+.3f}  |  cos(yaw): {cos_yaw:+.3f}")
            time.sleep(0.05)

    except KeyboardInterrupt:
        imu.shutdown()
        print("\n[BNO085] Stopped by user.")

    except Exception as e:
        print(f"[BNO085] Fatal error: {e}")
