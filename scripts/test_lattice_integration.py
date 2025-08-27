#!/usr/bin/env python3
"""
Test Lattice integration - verify entities and tasks
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lattice_drone_control.connectors.lattice import LatticeConnector
from src.lattice_drone_control.models.config import LatticeConfig

async def test_integration():
    """Test Lattice integration"""
    
    # Create config for new sandbox
    lattice_config = LatticeConfig(
        url="lattice-632d1.env.sandboxes.developer.anduril.com",
        use_grpc=True
    )
    
    connector = LatticeConnector(lattice_config)
    
    try:
        print("Testing Lattice Integration")
        print("=" * 50)
        
        # Connect
        await connector.connect()
        print("✓ Connected to Lattice")
        
        # Test 1: Publish a test entity
        print("\n1. Testing Entity Publishing...")
        test_telemetry = {
            "position": {"lat": 37.7749, "lon": -122.4194, "alt": 50.0},
            "battery": {"remaining_percent": 85},
            "status": "READY"
        }
        
        result = await connector.publish_entity("sitl-drone-1", test_telemetry)
        if result:
            print("✓ Successfully published entity to Lattice")
            print("  → Your drone should now be visible in the Lattice UI")
        else:
            print("✗ Failed to publish entity")
        
        # Test 2: Query for any existing tasks
        print("\n2. Querying for Tasks...")
        tasks = await connector.query_tasks()
        print(f"✓ Found {len(tasks)} tasks")
        for task in tasks:
            print(f"  → Task: {getattr(task, 'task_id', 'Unknown')}")
        
        # Test 3: Listen for tasks briefly
        print("\n3. Listening for new tasks (5 seconds)...")
        print("  → Try assigning a task to 'sitl-drone-1' in the Lattice UI")
        
        task_received = False
        async def task_callback(task):
            nonlocal task_received
            task_received = True
            print(f"  ✓ Received task: {getattr(task, 'task_id', 'Unknown')}")
        
        # Listen for 5 seconds
        listen_task = asyncio.create_task(connector.watch_tasks(task_callback))
        await asyncio.sleep(5)
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass
        
        if not task_received:
            print("  → No tasks received (this is normal if no tasks were assigned)")
        
        await connector.disconnect()
        print("\n✓ All tests completed")
        
        print("\n" + "=" * 50)
        print("Next Steps:")
        print("1. Open the Lattice UI in your browser")
        print("2. Look for entity 'sitl-drone-1' on the map")
        print("3. Try assigning a task to the drone")
        print("4. The middleware should receive and execute the task")
        
    except Exception as e:
        print(f"\n✗ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_integration()) 