#!/usr/bin/env python3
"""
Test script for relay task functionality
Tests various relay scenarios including single position, multi-position, and long duration
"""

import asyncio
import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, Any

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lattice_drone_control.core.middleware import DroneMiddleware
from src.lattice_drone_control.models.config import MiddlewareConfig
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_single_position_relay(middleware: DroneMiddleware, drone_id: str):
    """Test relay at a single position"""
    logger.info("Starting single position relay test")
    
    # Get drone connector
    connector = middleware.drone_connectors.get(drone_id)
    if not connector:
        logger.error(f"Drone {drone_id} not found")
        return False
    
    # Arm and takeoff
    logger.info("Arming drone...")
    if not await connector.arm():
        logger.error("Failed to arm drone")
        return False
    
    logger.info("Taking off to 50m...")
    if not await connector.takeoff(altitude=50.0):
        logger.error("Failed to takeoff")
        return False
    
    # Define relay position
    relay_params = {
        "relay_position": {
            "lat": -35.363261,
            "lon": 149.165230
        },
        "altitude": 100.0,
        "duration": 60  # 1 minute relay
    }
    
    # Execute relay task
    logger.info("Starting relay task...")
    success = await middleware.execute_task(drone_id, "relay", relay_params)
    
    if not success:
        logger.error("Failed to start relay task")
        return False
    
    # Monitor task for duration
    logger.info("Monitoring relay task for 60 seconds...")
    for i in range(60):
        status = await middleware.get_drone_status(drone_id)
        if status:
            position = status.get('position', {})
            logger.info(f"Progress: {i+1}/60s - Position: ({position.get('lat', 0):.6f}, {position.get('lon', 0):.6f})")
        await asyncio.sleep(1)
    
    # Stop task and RTL
    logger.info("Stopping task and returning to launch...")
    await middleware.stop_task(drone_id)
    
    return True


async def test_multi_position_relay(middleware: DroneMiddleware, drone_id: str):
    """Test relay with position changes"""
    logger.info("Starting multi-position relay test")
    
    # Get drone connector
    connector = middleware.drone_connectors.get(drone_id)
    if not connector:
        logger.error(f"Drone {drone_id} not found")
        return False
    
    # Arm and takeoff
    logger.info("Arming drone...")
    if not await connector.arm():
        logger.error("Failed to arm drone")
        return False
    
    logger.info("Taking off to 50m...")
    if not await connector.takeoff(altitude=50.0):
        logger.error("Failed to takeoff")
        return False
    
    # Test multiple relay positions
    positions = [
        {"lat": -35.363261, "lon": 149.165230},
        {"lat": -35.363461, "lon": 149.165430},
        {"lat": -35.363661, "lon": 149.165230}
    ]
    
    for idx, position in enumerate(positions):
        logger.info(f"Moving to relay position {idx + 1}/{len(positions)}")
        
        relay_params = {
            "relay_position": position,
            "altitude": 80.0 + (idx * 10),  # Vary altitude
            "duration": 30  # 30 seconds at each position
        }
        
        # Execute relay task
        success = await middleware.execute_task(drone_id, "relay", relay_params)
        
        if not success:
            logger.error(f"Failed to start relay task at position {idx + 1}")
            continue
        
        # Monitor for duration
        for i in range(30):
            status = await middleware.get_drone_status(drone_id)
            if status:
                current_pos = status.get('position', {})
                logger.info(f"Position {idx + 1} - {i+1}/30s - Alt: {current_pos.get('alt', 0):.1f}m")
            await asyncio.sleep(1)
    
    # Stop task and RTL
    logger.info("Stopping task and returning to launch...")
    await middleware.stop_task(drone_id)
    
    return True


async def test_long_duration_relay(middleware: DroneMiddleware, drone_id: str):
    """Test long duration relay mission"""
    logger.info("Starting long duration relay test")
    
    # Get drone connector
    connector = middleware.drone_connectors.get(drone_id)
    if not connector:
        logger.error(f"Drone {drone_id} not found")
        return False
    
    # Arm and takeoff
    logger.info("Arming drone...")
    if not await connector.arm():
        logger.error("Failed to arm drone")
        return False
    
    logger.info("Taking off to 80m...")
    if not await connector.takeoff(altitude=80.0):
        logger.error("Failed to takeoff")
        return False
    
    # Define long duration relay
    relay_params = {
        "relay_position": {
            "lat": -35.363261,
            "lon": 149.165230
        },
        "altitude": 120.0,
        "duration": 300  # 5 minute relay
    }
    
    # Execute relay task
    logger.info("Starting long duration relay task (5 minutes)...")
    success = await middleware.execute_task(drone_id, "relay", relay_params)
    
    if not success:
        logger.error("Failed to start relay task")
        return False
    
    # Monitor task for duration with periodic status updates
    logger.info("Monitoring relay task for 5 minutes...")
    for minute in range(5):
        logger.info(f"Relay minute {minute + 1}/5")
        for second in range(60):
            status = await middleware.get_drone_status(drone_id)
            if status and second % 10 == 0:  # Log every 10 seconds
                battery = status.get('battery', {}).get('remaining_percent', 0)
                logger.info(f"Time: {minute}:{second:02d} - Battery: {battery:.1f}%")
            await asyncio.sleep(1)
    
    # Stop task and RTL
    logger.info("Stopping task and returning to launch...")
    await middleware.stop_task(drone_id)
    
    return True


async def main():
    """Main test execution"""
    parser = argparse.ArgumentParser(description='Test relay task functionality')
    parser.add_argument('--config', type=str, default='config/single_drone.yaml',
                        help='Configuration file path')
    parser.add_argument('--test', type=str, default='all',
                        choices=['single', 'multi', 'long', 'all'],
                        help='Which test to run')
    parser.add_argument('--drone-id', type=str, default='sitl-drone-1',
                        help='Drone ID to test with')
    
    args = parser.parse_args()
    
    # Load configuration
    logger.info(f"Loading configuration from {args.config}")
    try:
        with open(args.config, 'r') as f:
            config_data = yaml.safe_load(f)
        if not isinstance(config_data, dict):
            raise ValueError("Configuration file must contain a dictionary")
        config = MiddlewareConfig.from_dict(config_data)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return
    
    # Create middleware
    middleware = DroneMiddleware(config)
    
    try:
        # Start middleware
        logger.info("Starting middleware...")
        await middleware.start()
        
        # Wait for connections to stabilize
        await asyncio.sleep(3)
        
        # Run selected tests
        if args.test == 'single' or args.test == 'all':
            await test_single_position_relay(middleware, args.drone_id)
            if args.test == 'all':
                await asyncio.sleep(5)
        
        if args.test == 'multi' or args.test == 'all':
            await test_multi_position_relay(middleware, args.drone_id)
            if args.test == 'all':
                await asyncio.sleep(5)
        
        if args.test == 'long' or args.test == 'all':
            await test_long_duration_relay(middleware, args.drone_id)
        
        logger.info("All tests completed")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Shutdown middleware
        logger.info("Shutting down middleware...")
        await middleware.shutdown()


if __name__ == "__main__":
    asyncio.run(main()) 