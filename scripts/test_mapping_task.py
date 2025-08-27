#!/usr/bin/env python3
"""
Test script for mapping task functionality
Tests various mapping scenarios including small area, large area, and custom parameters
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


async def test_small_area_mapping(middleware: DroneMiddleware, drone_id: str):
    """Test mapping a small 100m x 100m area"""
    logger.info("Starting small area mapping test")
    
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
    
    logger.info("Taking off to 20m...")
    if not await connector.takeoff(altitude=20.0):
        logger.error("Failed to takeoff")
        return False
    
    # Define small mapping area (100m x 100m)
    mapping_params = {
        "area_center": {
            "lat": -35.363261,
            "lon": 149.165230
        },
        "area_size": {
            "width": 100,
            "height": 100
        },
        "altitude": 20.0,
        "overlap": 0.7,
        "camera_fov": 30.0
    }
    
    # Execute mapping task
    logger.info("Starting mapping task...")
    success = await middleware.execute_task(drone_id, "mapping", mapping_params)
    
    if not success:
        logger.error("Failed to start mapping task")
        return False
    
    # Monitor task for 60 seconds
    logger.info("Monitoring mapping task for 60 seconds...")
    for i in range(60):
        status = await middleware.get_drone_status(drone_id)
        if status:
            logger.info(f"Progress: {i+1}/60s - Task: {status.get('task_status', 'Unknown')}")
        await asyncio.sleep(1)
    
    # Stop task and RTL
    logger.info("Stopping task and returning to launch...")
    await middleware.stop_task(drone_id)
    
    return True


async def test_large_area_mapping(middleware: DroneMiddleware, drone_id: str):
    """Test mapping a large 500m x 500m area"""
    logger.info("Starting large area mapping test")
    
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
    
    # Define large mapping area (500m x 500m)
    mapping_params = {
        "area_center": {
            "lat": -35.363261,
            "lon": 149.165230
        },
        "area_size": {
            "width": 500,
            "height": 500
        },
        "altitude": 50.0,
        "overlap": 0.8,
        "camera_fov": 30.0
    }
    
    # Execute mapping task
    logger.info("Starting large area mapping task...")
    success = await middleware.execute_task(drone_id, "mapping", mapping_params)
    
    if not success:
        logger.error("Failed to start mapping task")
        return False
    
    # Monitor task for 180 seconds (3 minutes)
    logger.info("Monitoring mapping task for 3 minutes...")
    for i in range(180):
        status = await middleware.get_drone_status(drone_id)
        if status:
            logger.info(f"Progress: {i+1}/180s - Task: {status.get('task_status', 'Unknown')}")
        await asyncio.sleep(1)
    
    # Stop task and RTL
    logger.info("Stopping task and returning to launch...")
    await middleware.stop_task(drone_id)
    
    return True


async def test_custom_mapping_parameters(middleware: DroneMiddleware, drone_id: str):
    """Test mapping with custom parameters"""
    logger.info("Starting custom parameters mapping test")
    
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
    
    # Define custom mapping parameters
    mapping_params = {
        "area_center": {
            "lat": -35.363261,
            "lon": 149.165230
        },
        "area_size": {
            "width": 200,
            "height": 150
        },
        "altitude": 30.0,
        "overlap": 0.6,  # Less overlap for faster coverage
        "camera_fov": 40.0,  # Wider FOV camera
        "mission_id": "test_custom_001"
    }
    
    # Execute mapping task
    logger.info("Starting custom mapping task...")
    success = await middleware.execute_task(drone_id, "mapping", mapping_params)
    
    if not success:
        logger.error("Failed to start mapping task")
        return False
    
    # Monitor task for 90 seconds
    logger.info("Monitoring mapping task for 90 seconds...")
    for i in range(90):
        status = await middleware.get_drone_status(drone_id)
        if status:
            logger.info(f"Progress: {i+1}/90s - Task: {status.get('task_status', 'Unknown')}")
        await asyncio.sleep(1)
    
    # Stop task and RTL
    logger.info("Stopping task and returning to launch...")
    await middleware.stop_task(drone_id)
    
    return True


async def main():
    """Main test execution"""
    parser = argparse.ArgumentParser(description='Test mapping task functionality')
    parser.add_argument('--config', type=str, default='config/single_drone.yaml',
                        help='Configuration file path')
    parser.add_argument('--test', type=str, default='all',
                        choices=['small', 'large', 'custom', 'all'],
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
        if args.test == 'small' or args.test == 'all':
            await test_small_area_mapping(middleware, args.drone_id)
            if args.test == 'all':
                await asyncio.sleep(5)  # Brief pause between tests
        
        if args.test == 'large' or args.test == 'all':
            await test_large_area_mapping(middleware, args.drone_id)
            if args.test == 'all':
                await asyncio.sleep(5)
        
        if args.test == 'custom' or args.test == 'all':
            await test_custom_mapping_parameters(middleware, args.drone_id)
        
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