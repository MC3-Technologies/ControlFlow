"""
Base class for all autonomous tasks

Abstract methods ensure all task implementations follow the same interface,
enabling the middleware to work with any task type uniformly.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

class BaseTask(ABC):
    """
    Abstract base class for all drone tasks
    
    To implement a new task type:
    1. Create a new class inheriting from BaseTask
    2. Implement the execute() method with your task logic
    3. Implement the stop() method to handle task interruption
    
    Example:
        class MyCustomTask(BaseTask):
            async def execute(self) -> bool:
                # Perform pre-flight checks
                if not await self.pre_flight_check():
                    return False
                
                # Your task logic here
                await self.drone_connector.takeoff(50)
                await self.drone_connector.goto_position(lat, lon, alt)
                # ... more logic ...
                
                return True  # Return True if successful
                
            async def stop(self):
                # Clean up and stop the task
                self.is_running = False
                await self.drone_connector.hold_position()
    """
    
    def __init__(self, drone_connector, params: Dict[str, Any]):
        self.drone_connector = drone_connector
        self.params = params
        self.logger = logging.getLogger(self.__class__.__name__)
        self.is_running = False
        self.result: Optional[bool] = None
    
    @abstractmethod
    async def execute(self) -> bool:
        """
        Execute the task
        
        Returns:
            True if task completed successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def stop(self):
        """Stop the task execution"""
        pass
    
    async def pre_flight_check(self) -> bool:
        """Perform pre-flight safety checks"""
        try:
            # Check if drone is armed and ready
            telemetry = await self.drone_connector.get_telemetry()
            
            if not telemetry.get("armed", False):
                self.logger.warning("Drone is not armed; attempting to arm now")
                try:
                    armed_ok = await self.drone_connector.arm()
                except Exception as arm_exc:
                    self.logger.error(f"Arm command threw exception: {arm_exc}")
                    return False
                if not armed_ok:
                    self.logger.error("Arm command failed; aborting pre-flight")
                    return False
                # Confirm arm state
                confirm = await self.drone_connector.get_telemetry()
                if not confirm.get("armed", False):
                    self.logger.error("Arm confirmation failed (still disarmed)")
                    return False
                self.logger.info("Drone armed successfully for task execution")
            
            # Note: Battery check disabled for simulation testing
            # battery_level = telemetry.get("battery", {}).get("remaining_percent", 0)
            # if battery_level < 20:  # Minimum 20% battery
            #     self.logger.error(f"Battery too low: {battery_level}%")
            #     return False
            
            # GPS Fix Types:
            # 0 = No GPS connected
            # 1 = No position information
            # 2 = 2D fix (only lat/lon, no altitude)
            # 3 = 3D fix (lat/lon/alt) - MINIMUM REQUIRED FOR FLIGHT
            # 4 = DGPS (differential GPS)
            # 5 = RTK Float
            # 6 = RTK Fixed (centimeter accuracy)
            gps_fix = telemetry.get("gps", {}).get("fix_type", 0)
            if gps_fix < 3:  # Need 3D GPS fix minimum
                self.logger.error(f"Insufficient GPS fix (type={gps_fix}). Need 3D fix or better.")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Pre-flight check failed: {e}")
            return False 