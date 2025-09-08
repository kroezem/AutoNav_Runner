# AutoNav Runner

On-device orchestration for our region-based indoor navigation system. This app wires together perception, planning, and control to drive a Raspberry Pi powered RC platform and a smart-cane prototype through a mapped building.

## At a glance
- Platform: Raspberry Pi 5 RC car and cane handle prototype
- Sensors: 360° LD19 LiDAR, BNO085 IMU, Pi Camera
- Navigation: region graph over ~49 regions with Visual Place Recognition (VPR) for localization
- Policy: PPO agent trained in Isaac Lab and run on-device
- Subsystems: safety checks, logging, telemetry UI, stub drivers for simulation
- Scope: site specific to one building and one hardware stack

## What this repo is
The thin runner that coordinates:
- **Drivers** for LiDAR, IMU, camera, PWM
- **Systems** for VPR, region navigation, safety, logging
- **Agents** for policy inference (RL or heuristic)
- **Controller** that closes the loop from sensors to actuation
- **App** for a minimal control surface and telemetry

## Repository layout
```
agents/       # trained policies
assets/       # configs and data (waypoints, VPR embeddings, etc.)
drivers/      # hardware IO: LiDAR, IMU, camera, PWM, serial
systems/      # VPR, region nav, safety, logging, telemetry
app.py        # Dash webapp UI to start/stop and view status
controller.py # main loop that wires everything together
```
