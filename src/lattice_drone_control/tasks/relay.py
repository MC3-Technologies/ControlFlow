"""
Communication relay task for extending network coverage
"""

import asyncio
from .base import BaseTask

class RelayTask(BaseTask):
    """
    Communication relay task that positions drone to extend network coverage
    """
    
    async def execute(self) -> bool:
        """Execute the relay mission"""
        try:
            self.logger.info("Starting relay task")
            self.is_running = True
            
            # Pre-flight checks
            if not await self.pre_flight_check():
                return False
            
            # Extract relay parameters
            relay_position = self.params.get("relay_position", {})
            altitude = self.params.get("altitude", 100)  # meters AGL
            duration = self.params.get("duration", 300)  # 5 minutes default
            
            # Move to relay position
            self.logger.info("Moving to relay position")
            success = await self.drone_connector.goto_position(
                relay_position["lat"],
                relay_position["lon"],
                altitude
            )
            
            if not success:
                self.logger.error("Failed to reach relay position")
                return False
            
            # Maintain position and provide relay service
            self.logger.info(f"Maintaining relay position for {duration} seconds")
            await self._maintain_relay_position(duration)
            
            self.logger.info("Relay task completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Relay task failed: {e}")
            return False
        finally:
            self.is_running = False
    
    async def stop(self):
        """Stop the relay task"""
        self.is_running = False
        await self.drone_connector.hold_position()
    
    async def _maintain_relay_position(self, duration: int):
        """Maintain position while providing relay service"""
        start_time = asyncio.get_event_loop().time()
        
        while self.is_running and (asyncio.get_event_loop().time() - start_time) < duration:
            # Monitor position drift and correct if necessary
            current_pos = await self.drone_connector.get_position()
            target_pos = self.params.get("relay_position", {})
            
            # Calculate distance from target
            distance = self._calculate_distance(current_pos, target_pos)
            
            if distance > 5:  # 5 meter tolerance
                self.logger.info("Correcting position drift")
                await self.drone_connector.goto_position(
                    target_pos["lat"],
                    target_pos["lon"],
                    self.params.get("altitude", 100)
                )
            
            # Update relay status in telemetry
            await self._update_relay_status()
            
            await asyncio.sleep(5)  # Check every 5 seconds
    
    def _calculate_distance(self, pos1: dict, pos2: dict) -> float:
        """Calculate distance between two positions in meters"""
        import math
        
        R = 6371000  # Earth radius in meters
        lat1_rad = math.radians(pos1["lat"])
        lat2_rad = math.radians(pos2["lat"])
        delta_lat = math.radians(pos2["lat"] - pos1["lat"])
        delta_lon = math.radians(pos2["lon"] - pos1["lon"])
        
        a = (math.sin(delta_lat/2) * math.sin(delta_lat/2) +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon/2) * math.sin(delta_lon/2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    async def _update_relay_status(self):
        """Update relay communication status"""
        # This would interface with communication systems
        # For now, just log status
        self.logger.debug("Relay active - providing communication coverage") 