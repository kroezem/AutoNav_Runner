import time, math, torch
from queue import Empty, Queue
from systems.subsystem import Subsystem
import torch.nn as nn


class GaussianPolicy(nn.Module):
    def __init__(self, input_size=34, hidden_size=256, output_size=2):
        super().__init__()
        self.net_container = nn.Sequential(
            nn.Linear(input_size, hidden_size), nn.ELU(),
            nn.Linear(hidden_size, hidden_size), nn.ELU()
        )
        self.policy_layer = nn.Linear(hidden_size, output_size)
        self.value_layer = nn.Linear(hidden_size, 1)
        self.log_std_parameter = nn.Parameter(torch.zeros(output_size))

    def forward(self, x):
        feat = self.net_container(x)
        return self.policy_layer(feat), self.value_layer(feat)


# ────────────────────────────────────────────────────────────────────────────

class Inference(Subsystem):
    """Thread that converts sensor observations → (throttle, steer)."""

    def __init__(self, state, obs_q: Queue, act_q: Queue, hz: float = 30.0):
        super().__init__(state, name="inference")
        self.obs_q = obs_q
        self.act_q = act_q
        self.dt = 1 / hz
        self.model = None  # call load_model() before start()
        self.last_action = torch.zeros(2)

    def load_model(self, ckpt_path: str):
        self.model = GaussianPolicy()
        self.model.load_state_dict(torch.load(ckpt_path, map_location="cpu")["policy"], strict=False)
        self.model.eval()

    def _obs_to_tensor(self, o: dict) -> torch.Tensor:
        vec = (
                self.last_action.tolist() +
                o["lidar"] +
                [o["gyro_z"], o["accel_x"] / 9.81, o["sin_yaw"], o["cos_yaw"]]
        )
        return torch.tensor(vec, dtype=torch.float32)

    def loop(self):
        t0 = time.perf_counter()

        try:
            obs = self.obs_q.get_nowait()
            while not self.obs_q.empty():  # discard stale
                obs = self.obs_q.get_nowait()
        except Empty:
            time.sleep(0.002)
            return

        if self.model is None:
            return

        with torch.no_grad():
            action, _ = self.model(self._obs_to_tensor(obs).unsqueeze(0))
        throttle, steer = action.squeeze(0).tolist()
        self.last_action = action.squeeze(0)

        # Clamp and push to queue
        throttle = max(-1, min(1, throttle))
        steer = max(-1, min(1, steer))
        while not self.act_q.empty():
            try:
                self.act_q.get_nowait()
            except Empty:
                break
        self.act_q.put_nowait((throttle, steer))

        self.publish(throttle=throttle, steering=steer, loop="running")

        dt = time.perf_counter() - t0
        if dt < self.dt:
            time.sleep(self.dt - dt)
