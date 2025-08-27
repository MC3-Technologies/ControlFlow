import asyncio
import yaml
import sys
import logging
from pathlib import Path
from typing import Any, Dict

# Configure logging to see task execution details
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Ensure project root is on PYTHONPATH so that `import src...` works regardless of cwd
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lattice_drone_control.core.middleware import DroneMiddleware
from src.lattice_drone_control.models.config import MiddlewareConfig


def load_config(path: str = "config/default.yaml") -> MiddlewareConfig:
    """Load YAML config file and convert to MiddlewareConfig."""
    data: Dict[str, Any] = yaml.safe_load(Path(path).read_text())  # type: ignore[no-any-unbound]
    return MiddlewareConfig.from_dict(data)


async def demo() -> None:
    """Run a short end-to-end task against the SITL drone."""
    print("\n=== Starting Mapping Task Demo ===\n", flush=True)
    
    try:
        print("Loading config...", flush=True)
        cfg = load_config("config/single_drone.yaml")  # Use single drone config
        print("Config loaded successfully", flush=True)
        
        print("Creating middleware...", flush=True)
        mw = DroneMiddleware(cfg)

        print("1. Starting middleware...", flush=True)
        await mw.start()
        print("   Middleware started!", flush=True)

        # Grab the connector so we can arm & takeoff before the mapping mission
        print("Getting drone connector...", flush=True)
        connector = mw.drone_connectors.get("sitl-drone-1")
        if connector is None:
            print("ERROR: sitl-drone-1 not found in connectors!", flush=True)
            print(f"Available connectors: {list(mw.drone_connectors.keys())}", flush=True)
            raise RuntimeError("sitl-drone-1 not connected – check SITL & MAVSDK server")

        print("2. Arming drone...", flush=True)
        armed = await connector.arm()
        print(f"   Arm result: {armed}", flush=True)
        
        print("3. Taking off to 20m...", flush=True)
        takeoff_result = await connector.takeoff(altitude=20.0)
        print(f"   Takeoff result: {takeoff_result}", flush=True)
        
        if not takeoff_result:
            print("Takeoff failed – aborting demo", flush=True)
            await mw.shutdown()
            return

        print("4. Starting mapping task...", flush=True)
        params = {"area_center": {"lat": 47.3978, "lon": 8.5456}, "area_size": {"width": 100, "height": 100}, "altitude": 20}
        task_started = await mw.execute_task("sitl-drone-1", "mapping", params)
        print(f"   Task started: {task_started}", flush=True)

        print("5. Letting mapping task run for 30 seconds...", flush=True)
        print("   Watch the map window to see the drone fly a grid pattern!", flush=True)
        
        # Let the task run for 30 seconds
        for i in range(30):
            print(f"   Running... {i+1}/30 seconds", flush=True)
            await asyncio.sleep(1)

        print("6. Stopping task and returning to launch...", flush=True)
        # Stop task and shut down
        await mw.stop_task("sitl-drone-1")
        
        print("7. Shutting down middleware...", flush=True)
        await mw.shutdown()
        
        print("\n=== Demo Complete ===\n", flush=True)
        
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("Starting test script...", flush=True)
    asyncio.run(demo())
    print("Test script finished", flush=True)