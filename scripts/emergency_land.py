#!/usr/bin/env python3
"""
Emergency landing script to safely land a drone that's stuck in the air
"""

import asyncio
import sys
import logging
from pathlib import Path

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lattice_drone_control.connectors.mavsdk import MAVSDKConnector
from src.lattice_drone_control.models.config import DroneConfig

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def emergency_land():
    """Emergency landing for a drone that's stuck in the air"""
    # Create a simple drone config
    drone_config = DroneConfig(
        id="sitl-drone-1",
        connection_string="udp://:14550",
        type="quadcopter",
        manufacturer="ArduPilot",
        model="SITL",
        capabilities=["mapping", "relay", "dropping"],
        max_altitude=120.0,
        max_speed=20.0,
        max_flight_time=1800,
        geofence_enabled=True,
        rtl_altitude=50.0,
        failsafe_action="RTL"
    )
    
    connector = MAVSDKConnector(drone_config)
    
    print("Connecting to drone...")
    await connector.connect()
    
    print("Getting telemetry...")
    telemetry = await connector.get_telemetry()
    print(f"Telemetry: {telemetry}")
    
    if telemetry.get('armed', False):
        print("Drone is armed - initiating emergency landing...")
        
        print("Returning to launch...")
        rtl_result = await connector.return_to_launch()
        print(f"RTL result: {rtl_result}")
        
        # Wait for landing
        print("Waiting for landing...")
        await asyncio.sleep(15)
        
        print("Checking if drone has landed...")
        final_telemetry = await connector.get_telemetry()
        print(f"Final telemetry: {final_telemetry}")
        
        if final_telemetry.get('armed', False):
            print("Drone still armed - attempting manual disarm...")
            disarm_result = await connector.disarm()
            print(f"Disarm result: {disarm_result}")
    else:
        print("Drone is not armed - no emergency landing needed")
    
    print("Disconnecting...")
    await connector.disconnect()

if __name__ == "__main__":
    asyncio.run(emergency_land()) 