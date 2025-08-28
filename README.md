# Lattice-Native Drone Control System

A production-ready middleware solution that bridges Anduril's Lattice mission command software with drone flight controllers, enabling autonomous task switching and comprehensive telemetry management.

## Overview

This system implements a Lattice-native approach where each drone is represented as an entity in Lattice, receives tasks through the Lattice Task Manager, and reports telemetry back to Lattice. The middleware enables seamless switching between different autonomous tasks (mapping, relay, dropping) without manual intervention.

## Architecture

```
Lattice Platform (gRPC/HTTP)
        ↕
Middleware Layer (Python)
        ↕
MAVLink Protocol
        ↕
Drone Flight Controllers (CubePilot/ArduPilot)
```

## Features

- **Lattice Native Integration**: Full integration with Lattice SDK for entity management and task execution
- **Multi-Drone Support**: Manage up to 5 drones concurrently (expandable to 50+)
- **Autonomous Task Switching**: On-the-fly switching between mapping, relay, and dropping tasks
- **Real-time Telemetry**: 4Hz position updates, 1Hz system status updates
- **Production Ready**: Comprehensive error handling, metrics, and monitoring
- **SITL Testing**: Full support for Software-In-The-Loop testing with ArduPilot

## Prerequisites

- Python 3.10+
- Windows 11 with WSL 2 (for the recommended dev workflow) or Linux
- ArduPilot SITL tools (for testing; installed inside WSL/Linux)
- Docker (optional, for containerized deployment)
- Lattice SDK (installed via requirements)
- Lattice platform credentials if using production config

## Important: Lattice Platform Access

This middleware requires access to Anduril's Lattice platform. The default configuration contains placeholder URLs that must be replaced:

1. **Install the SDK**: The SDK is publicly available on PyPI:
   ```bash
   pip install anduril-lattice-sdk  # Already included in requirements.txt
   ```

2. **Get Platform Access**: Contact Anduril Industries for:
   - Your Lattice instance URL (replaces `your-lattice-instance.anduril.com`)
   - Authentication tokens (Bearer token)
   - API documentation and support

3. **Update Configuration**: Once you have credentials:
   - `.env`: Add your `LATTICE_BEARER_TOKEN`
             Add your `LATTICE_URL`

The code includes fallback mock classes for development/testing when you don't have platform credentials yet.

## Installation

1. Clone the repository:
```bash
git clone https://github.com/MC3-Technologies/ControlFlow.git
cd ControlFlow
```

2. Create a virtual environment:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your LATTICE_BEARER_TOKEN, LATTICE_URL, and SANDBOXES_TOKEN
```

## Configuration

Edit `config/default.yaml` or `config/lattice_production.yaml`to configure:
- Lattice connection settings
- Drone connection strings
- Safety parameters
- Telemetry rates

Example drone configuration:
```yaml
drones:
  - drone_id: DRONE-001
    connection_string: udp://:14540
    type: quadcopter
    manufacturer: CubePilot
    model: CubeOrange
    capabilities:
      - mapping
      - relay
      - dropping
```

## Running the Middleware

### SITL prerequisites and notes

- ArduPilot SITL must be installed in WSL/Linux. Install via the official docs below. The quick-start assumes `sim_vehicle.py` is on your PATH in WSL.
- MAVSDK server binary is included under `mavsdk_server/`. If missing, run:
  ```powershell
  python scripts\setup_mavsdk_server.py
  ```
- `scripts/start_px4_sitl_swarm.py` is experimental and primarily demonstrates port wiring; use ArduPilot for end-to-end testing.

### Install references

- ArduPilot SITL (Linux/WSL): see `https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html` and the Linux build instructions at `https://ardupilot.org/dev/docs/building-setup-linux.html`.
- MAVProxy (required by many ArduPilot workflows): see `https://ardupilot.github.io/MAVProxy/html/index.html` → Installation for your platform.

### Development vs Production

- **Development mode**: run against SITL, optional mock Lattice; fast iteration, verbose logging, local files. Use `config\default.yaml`.
- **Production mode**: connect to real Lattice and real airframes; controlled logging, Dockerized runtime, persistent configuration. Use `config\lattice_production.yaml`.

The only difference is which config and environment variables you provide. Code paths are the same.

### Windows + WSL Quick Start (Single Drone)

1) In WSL, start ArduPilot SITL and stream MAVLink to Windows:
```bash
WINDOWS_IP=$(grep nameserver /etc/resolv.conf | awk '{print $2}')
sim_vehicle.py -v ArduCopter -f quad --sysid 1 \
               --out udp:${WINDOWS_IP}:14550 \
               --console --map
```

2) In Windows PowerShell, start MAVSDK server (single drone: gRPC 50050, UDP 14550):
```powershell
./start_mavsdk_server_minimal.bat
```

3) Run the middleware (HTTP/REST; keep `LATTICE_USE_GRPC=false`).

Docker (recommended):
See [Docker Deployment](#docker-deployment) below to set up the image and env-file first.
```powershell
# Build once (from repo root) if you haven't already
docker build -f docker\Dockerfile.middleware -t lattice-drone-middleware .

# Run with env-file; edit docker\middleware.env first
docker run -d `
  --name lattice-drone-middleware `
  --env-file docker\middleware.env `
  -p 9090:9090 `
  -v ${PWD}\config:/app/config:ro `
  -v ${PWD}\logs:/app/logs `
  lattice-drone-middleware `
  python -m src.lattice_drone_control.main --config config/lattice_production.yaml
```

Bare Python (alternative):
```powershell
# Development (mock Lattice)
python -m src.lattice_drone_control.main --config config\default.yaml

# Production (real Lattice)
python -m src.lattice_drone_control.main --config config\lattice_production.yaml
```

4) Optional checks and sample tasks:
```powershell
python scripts\health_check.py --config config\default.yaml
python scripts\test_tasks.py
```

Tip: The `time moved backwards` messages in MAVProxy are harmless.

### Multi-Drone

Not currently supported in this guide. Focus is single-drone using `start_mavsdk_server_minimal.bat`. Multi-drone instructions is in progress and will be added once stabilized.

## Task Types

### Mapping Task
Autonomous area survey with configurable patterns:
- Lawn mower search pattern
- Configurable overlap and altitude
- Automatic photo capture

### Relay Task (in progress)
Communication relay positioning:
- Maintain specific position for network extension
- Automatic position correction
- Configurable duration

### Dropping Task (in progress)
Payload delivery to specified locations:
- Multiple drop points support
- Safe altitude approach
- Wind condition checking

Note: At the moment, only the Mapping task is fully functional; Relay and Dropping are in progress.

## API Usage

The middleware automatically watches for tasks assigned through Lattice. Tasks can be created using the Lattice UI or API:

```python
# Example task creation (via Lattice SDK)
task = {
    "task_id": "TASK-123",
    "task_type": "mapping",
    "target_entity_id": "DRONE-001",
    "parameters": {
        "area_center": {"lat": 37.4419, "lon": -122.1430},
        "area_size": {"width": 100, "height": 100},
        "altitude": 50,
        "overlap": 0.8
    }
}
```

## Monitoring

### Prometheus Metrics
Access metrics at `http://localhost:9090/metrics`:
- Drone connections and status
- Task execution statistics
- Telemetry update rates
- Error counts

### Logging
Structured JSON logging with levels:
- INFO: Normal operations
- WARNING: Recoverable issues
- ERROR: Failures requiring attention

## Development

### SITL Testing (In progress)
```bash
# Run specific SITL test scenarios
python tests/sitl/test_multi_drone.py
```

## Deployment

### Docker Deployment

Create `docker/middleware.env` from the provided example and edit token/URL values.

Environment flags

- LATTICE_BEARER_TOKEN: Bearer token for Lattice authentication (preferred variable name)
- LATTICE_URL: Base hostname for your Lattice instance (e.g., lattice-xxxx.env.sandboxes.developer.anduril.com)
- MAVSDK_SERVER_HOST: Hostname/IP of MAVSDK server as seen from container. Use `host.docker.internal` on Windows/Mac; use host IP on Linux
- LATTICE_USE_GRPC: Set to `true` only if you have Anduril gRPC stubs and want gRPC. When false/unset, missing gRPC logs are demoted to debug
- LATTICE_SDK_LOCAL: Set to `true` to prefer the vendored `lattice-sdk-python` copy over the pip-installed SDK. Default prefers pip and falls back to vendored if present

Using an env-file (recommended)

1) Create an env file at `docker/middleware.env` (or copy from `docker/middleware.env.example` if present):

```ini
# docker/middleware.env
LATTICE_BEARER_TOKEN=your_bearer_token
# Required for sandboxes.* environments
SANDBOXES_TOKEN=your_sandboxes_token
LATTICE_URL=lattice-XXXX.env.sandboxes.developer.anduril.com

# Networking from container to host MAVSDK server
MAVSDK_SERVER_HOST=host.docker.internal

# Runtime toggles
LATTICE_USE_GRPC=false
# Prefer pip SDK (default); set to true to force vendored SDK if present
LATTICE_SDK_LOCAL=false
```

2) Build the image:

```bash
docker build -f docker/Dockerfile.middleware -t lattice-drone-middleware .
```

3a) Run with env-file (bash):

```bash
docker run -d \
  --name lattice-drone-middleware \
  --env-file docker/middleware.env \
  -p 9090:9090 \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/logs:/app/logs \
  lattice-drone-middleware \
  python -m src.lattice_drone_control.main --config config/lattice_production.yaml
```

3b) Run with env-file (Windows PowerShell):

```powershell
docker run -d `
  --name lattice-drone-middleware `
  --env-file docker\middleware.env `
  -p 9090:9090 `
  -v ${PWD}\config:/app/config:ro `
  -v ${PWD}\logs:/app/logs `
  lattice-drone-middleware `
  python -m src.lattice_drone_control.main --config config/lattice_production.yaml
```

Manual build/run:
```bash
docker build -f docker/Dockerfile.middleware -t lattice-drone-middleware .
docker run -d \
  --name lattice-drone-middleware \
  -e LATTICE_BEARER_TOKEN=your_token \
  -e SANDBOXES_TOKEN=your_sandboxes_token \
  -e LATTICE_URL=lattice-xxxx.env.sandboxes.developer.anduril.com \
  -e METRICS_ENABLED=true \
  -e METRICS_PORT=9090 \
  -e MAVSDK_SERVER_HOST=host.docker.internal \
  -e LATTICE_USE_GRPC=false \
  # uncomment if you want to force the vendored SDK copy
  # -e LATTICE_SDK_LOCAL=false \
  -p 9090:9090 \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/logs:/app/logs \
  lattice-drone-middleware
```



## Safety Features

- Minimum battery threshold (20%)
- Geofencing support
- Automatic Return-to-Launch on connection loss
- Wind speed monitoring
- Failsafe actions

## Troubleshooting

### Common Issues

1. **Connection to Lattice fails**
   - Verify LATTICE_TOKEN is set
   - Check network connectivity
   - Ensure Lattice URL is correct

2. **Drone won't connect**
   - Verify connection string format
   - Check if SITL is running
   - Ensure no port conflicts

3. **Task execution fails**
   - Check drone is armed and ready
   - Verify GPS fix is available
   - Review task parameters

### Debug Mode
```bash
python -m src.lattice_drone_control.main --log-level DEBUG
```

### Verify SDK Installation
```bash
python scripts/verify_sdk.py
```

## Performance

- Supports 5 concurrent drones (in-testing)
- Architected for 50+ drones
- 4Hz telemetry updates
- <100ms command acknowledgment
- <500ms task switching

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

Proprietary - See LICENSE file

## Support

- Documentation: docs/
- Issues: GitHub Issues
- Email: imatar@mc3technologies.com

## Acknowledgments

- Anduril Industries for Lattice SDK
- ArduPilot community
- MAVSDK contributors 