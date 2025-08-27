#!/usr/bin/env python3
"""
Test script for dropping task functionality
Tests various dropping scenarios including single drop, multiple drops, and precision drops
"""

import asyncio
import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, List

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


async def test_single_drop(middleware: DroneMiddleware, drone_id: str):
    """Test single payload drop"""
    logger.info("Starting single drop test")
    
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
    
    logger.info("Taking off to 30m...")
    if not await connector.takeoff(altitude=30.0):
        logger.error("Failed to takeoff")
        return False
    
    # Define single drop location
    drop_params = {
        "drop_locations": [
            {
                "lat": -35.363261,
                "lon": 149.165230,
                "description": "Drop Zone Alpha"
            }
        ],
        "approach_altitude": 50.0,
        "drop_altitude": 10.0
    }
    
    # Execute dropping task
    logger.info("Starting dropping task...")
    success = await middleware.execute_task(drone_id, "dropping", drop_params)
    
    if not success:
        logger.error("Failed to start dropping task")
        return False
    
    # Monitor task completion
    logger.info("Monitoring dropping task...")
    task_complete = False
    for i in range(60):  # Max 60 seconds
        status = await middleware.get_drone_status(drone_id)
        if status:
            task_status = status.get('task_status', '')
            position = status.get('position', {})
            logger.info(f"Progress: {i+1}/60s - Status: {task_status} - Alt: {position.get('alt', 0):.1f}m")
            
            if task_status in ['COMPLETED', 'FAILED', 'CANCELLED']:
                task_complete = True
                break
        await asyncio.sleep(1)
    
    if task_complete:
        logger.info(f"Task completed with status: {task_status}")
    else:
        logger.warning("Task did not complete within timeout")
    
    # Stop task and RTL
    logger.info("Returning to launch...")
    await middleware.stop_task(drone_id)
    
    return True


async def test_multiple_drops(middleware: DroneMiddleware, drone_id: str):
    """Test multiple payload drops in sequence"""
    logger.info("Starting multiple drops test")
    
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
    
    logger.info("Taking off to 40m...")
    if not await connector.takeoff(altitude=40.0):
        logger.error("Failed to takeoff")
        return False
    
    # Define multiple drop locations
    drop_params = {
        "drop_locations": [
            {
                "lat": -35.363261,
                "lon": 149.165230,
                "description": "Drop Zone 1"
            },
            {
                "lat": -35.363461,
                "lon": 149.165430,
                "description": "Drop Zone 2"
            },
            {
                "lat": -35.363661,
                "lon": 149.165630,
                "description": "Drop Zone 3"
            }
        ],
        "approach_altitude": 60.0,
        "drop_altitude": 15.0
    }
    
    # Execute dropping task
    logger.info(f"Starting dropping task with {len(drop_params['drop_locations'])} drop zones...")
    success = await middleware.execute_task(drone_id, "dropping", drop_params)
    
    if not success:
        logger.error("Failed to start dropping task")
        return False
    
    # Monitor task completion
    logger.info("Monitoring multiple drops...")
    drop_count = 0
    last_position = None
    
    for i in range(180):  # Max 3 minutes
        status = await middleware.get_drone_status(drone_id)
        if status:
            task_status = status.get('task_status', '')
            position = status.get('position', {})
            
            # Detect position changes (indicating movement to new drop zone)
            current_position = (position.get('lat', 0), position.get('lon', 0))
            if last_position and abs(current_position[0] - last_position[0]) > 0.0001:
                drop_count += 1
                logger.info(f"Moved to drop zone {drop_count}")
            last_position = current_position
            
            if i % 10 == 0:  # Log every 10 seconds
                logger.info(f"Progress: {i+1}/180s - Status: {task_status} - Alt: {position.get('alt', 0):.1f}m")
            
            if task_status in ['COMPLETED', 'FAILED', 'CANCELLED']:
                break
        await asyncio.sleep(1)
    
    logger.info(f"Task completed. Estimated drops performed: {drop_count}")
    
    # Stop task and RTL
    logger.info("Returning to launch...")
    await middleware.stop_task(drone_id)
    
    return True


async def test_precision_drop(middleware: DroneMiddleware, drone_id: str):
    """Test precision drop with specific parameters"""
    logger.info("Starting precision drop test")
    
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
    
    logger.info("Taking off to 25m...")
    if not await connector.takeoff(altitude=25.0):
        logger.error("Failed to takeoff")
        return False
    
    # Define precision drop with custom parameters
    drop_params = {
        "drop_locations": [
            {
                "lat": -35.363361,
                "lon": 149.165330,
                "description": "Precision Target"
            }
        ],
        "approach_altitude": 40.0,
        "drop_altitude": 5.0,  # Very low altitude for precision
        "position_tolerance": 0.5,  # Tighter tolerance
        "stabilization_time": 5.0,  # Longer stabilization
        "payload_type": "precision_package"
    }
    
    # Execute dropping task
    logger.info("Starting precision dropping task...")
    success = await middleware.execute_task(drone_id, "dropping", drop_params)
    
    if not success:
        logger.error("Failed to start dropping task")
        return False
    
    # Monitor task with detailed position tracking
    logger.info("Monitoring precision drop...")
    target_lat = drop_params['drop_locations'][0]['lat']
    target_lon = drop_params['drop_locations'][0]['lon']
    
    for i in range(90):  # Max 90 seconds
        status = await middleware.get_drone_status(drone_id)
        if status:
            task_status = status.get('task_status', '')
            position = status.get('position', {})
            
            # Calculate distance to target
            lat_diff = abs(position.get('lat', 0) - target_lat) * 111000  # meters
            lon_diff = abs(position.get('lon', 0) - target_lon) * 111000  # meters
            distance = (lat_diff**2 + lon_diff**2)**0.5
            
            logger.info(f"Progress: {i+1}/90s - Distance to target: {distance:.2f}m - Alt: {position.get('alt', 0):.1f}m")
            
            if task_status in ['COMPLETED', 'FAILED', 'CANCELLED']:
                break
        await asyncio.sleep(1)
    
    # Stop task and RTL
    logger.info("Returning to launch...")
    await middleware.stop_task(drone_id)
    
    return True


async def main():
    """Main test execution"""
    parser = argparse.ArgumentParser(description='Test dropping task functionality')
    parser.add_argument('--config', type=str, default='config/single_drone.yaml',
                        help='Configuration file path')
    parser.add_argument('--test', type=str, default='all',
                        choices=['single', 'multiple', 'precision', 'all'],
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
            await test_single_drop(middleware, args.drone_id)
            if args.test == 'all':
                await asyncio.sleep(5)
        
        if args.test == 'multiple' or args.test == 'all':
            await test_multiple_drops(middleware, args.drone_id)
            if args.test == 'all':
                await asyncio.sleep(5)
        
        if args.test == 'precision' or args.test == 'all':
            await test_precision_drop(middleware, args.drone_id)
        
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