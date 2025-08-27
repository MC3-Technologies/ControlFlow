#!/usr/bin/env python3
"""
Simple script to test MAVSDK connection and takeoff
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

async def test_drone_connection():
    """Test connection to the drone and attempt a simple takeoff"""
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
    
    print("Attempting to arm the drone...")
    arm_result = await connector.arm()
    print(f"Arm result: {arm_result}")
    
    if arm_result:
        print("Attempting takeoff to 5 meters...")
        takeoff_result = await connector.takeoff(altitude=5.0)
        print(f"Takeoff result: {takeoff_result}")
        
        if takeoff_result:
            print("Waiting 5 seconds at altitude...")
            await asyncio.sleep(5)
            
            print("Returning to launch...")
            rtl_result = await connector.return_to_launch()
            print(f"RTL result: {rtl_result}")
            
            # Wait for landing
            print("Waiting for landing...")
            await asyncio.sleep(10)
        else:
            print("Takeoff failed, skipping RTL.")
    else:
        print("Arming failed, skipping takeoff.")
    
    print("Disconnecting...")
    await connector.disconnect()

if __name__ == "__main__":
    asyncio.run(test_drone_connection()) 