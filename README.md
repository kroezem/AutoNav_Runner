# AutoNav Runner

AutoNav platform application for running the on-device stack that drives the RC platform and smart-cane prototype. It wires together perception, planning, and control subsystems and exposes a simple web app runner to start or stop inference and VPR systems.

## TL;DR
- `python app.py` starts the UI and runner, `python controller.py` runs the headless controller.
- Visual Place Recognition (VPR) **embeddings are not included**. You must regenerate them and drop the file in `assets/` before running. See **VPR embeddings** below.
- Folders: `agents/` learned policies, `systems/` higher level subsystems, `drivers/` hardware and IO shims, `assets/` configs and data.

## Why this repo
This repo is the thin orchestration layer that glues your subsystems together:
- **Controller** coordinates sensor IO, policy inference, and actuation.
- **App** provides a small control surface for starting or pausing the stack and for basic telemetry.
- **Modular layout** lets you swap policies, switch between sim and real hardware, and stub drivers for offline work.

## Repo layout
```
agents/      # RL or heuristic agents, loading and inference wrappers
assets/      # config and data blobs (waypoints, VPR embeddings, etc.)
drivers/     # hardware and IO: LiDAR, IMU, camera, PWM, serial
systems/     # higher level systems: VPR, region nav, safety, logging
app.py       # UI entry point, launches the runner
controller.py# core control loop and subsystem wiring
```

## Requirements
- Python 3.10 or newer
- Install to deps to global python installation as GPIO libs need root access/

## VPR embeddings
VPR region embeddings are ~90 MB so they are not checked into Git. To run this repo you must provide them locally.
1. Use your VPR pipeline to regenerate region embeddings for your environment or floorplan. Export as a JSON.
2. Place the file in `assets/`, for example `assets/region_embeddings.json`.
3. If your code expects a different filename or path, update that path in your config or loader.
4. If you change environments, regenerate the embeddings for that map to keep recognition consistent.

## Running
Headless controller:
```bash
python controller.py
```

With UI:
```bash
python app.py
```
