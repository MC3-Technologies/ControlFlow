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
- Windows 11 (development) or Linux (production)
- ArduPilot SITL (for testing)
- Docker (optional, for containerized deployment)
- Lattice SDK (available on PyPI: `pip install anduril-lattice-sdk`)
- Lattice platform credentials (contact Anduril for access)

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
git clone https://github.com/hima700/lattice-drone-control.git
cd lattice-drone-control
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

Edit `config/default.yaml` to configure:
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

### Development Mode

1. Start ArduPilot SITL instances:
```bash
python scripts/start_sitl_swarm.py -n 5
```

2. Run the middleware:
```bash
python -m src.lattice_drone_control.main
```

### Production Mode

Using Docker:
```bash
docker-compose up -d
```

Or as a systemd service:
```bash
sudo systemctl start lattice-drone-middleware
```

### SITL Quick-Start (Single-Drone, Local)

Follow this sequence whenever you want to bring the full stack up on a developer workstation.

1. **Start ArduPilot SITL inside WSL**  
   Find the Windows-host IP the WSL VM can reach and launch the simulator:
   ```bash
   WINDOWS_IP=$(grep nameserver /etc/resolv.conf | awk '{print $2}')
   sim_vehicle.py -v ArduCopter -f quad --sysid 1 \
                  --out udp:${WINDOWS_IP}:14550 \
                  --console --map          # omit --map if NumPy/OpenCV mismatch
   ```
   The white *ArduCopter* console window will appear and begin streaming MAVLink on UDP 14540.

2. **Start MAVSDK-server on Windows** (PowerShell, project root):
   ```powershell
   .\start_mavsdk_server_minimal.bat
   ```
   Wait for the line `System discovered` – this confirms MAVSDK-server received the MAVLink stream and opened gRPC 50040.

3. **Run the middleware in mock-mode** (no real Lattice creds required):
   ```powershell
   python -m src.lattice_drone_control.main --config config\default.yaml
   ```
   You should see `Connected to drone sitl-drone-1` in the log.

4. **Verify / exercise**
   *Health check*
   ```powershell
   python scripts\health_check.py --config config\default.yaml   # run from repo root
   ```
   *Sample autonomous tasks*
   ```powershell
   python scripts\test_tasks.py
   ```

5. **Manual control (optional)**  
   From the ArduPilot console:
   ```
   mode GUIDED
   arm throttle
   takeoff 5
   ```

> Tip: the repeated `time moved backwards` lines in MAVProxy are harmless.  Run SITL without MAVProxy (`--no-mavproxy`) if you want an entirely clean console.

### Multi-Drone SITL Swarm

1. Launch multiple SITL instances:
   ```bash
   python scripts/start_px4_sitl_swarm.py -n 3          # or start_sitl_swarm.py
   ```
2. Start matching MAVSDK-servers:
   ```powershell
   .\start_mavsdk_servers.bat                          # spawns ports 50040-50044
   ```
3. Add additional drone blocks to `config/default.yaml` with `connection_string` ports 14541…14544 and restart the middleware.

Now you can issue mapping/relay/dropping tasks to any of the simulated drones.

## Task Types

### Mapping Task
Autonomous area survey with configurable patterns:
- Lawn mower search pattern
- Configurable overlap and altitude
- Automatic photo capture

### Relay Task
Communication relay positioning:
- Maintain specific position for network extension
- Automatic position correction
- Configurable duration

### Dropping Task
Payload delivery to specified locations:
- Multiple drop points support
- Safe altitude approach
- Wind condition checking

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

### Running Tests
```bash
pytest tests/
pytest tests/unit/ -v
pytest tests/integration/ --cov
```

### Code Quality
```bash
black src/
flake8 src/
mypy src/
```

### SITL Testing
```bash
# Run specific SITL test scenarios
python tests/sitl/test_multi_drone.py
```

## Deployment

### Docker Deployment

Using Docker Compose (recommended):
```bash
docker compose up -d
```

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

PowerShell helpers (Windows):
```powershell
./scripts/docker_build.ps1
./scripts/docker_up.ps1
```

### Kubernetes Deployment
```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
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

- Supports 5 concurrent drones (tested)
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