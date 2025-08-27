"""
Entity Manager - Publishes drone telemetry to Lattice as entities
"""

import asyncio
import logging
from typing import Dict, Any
from datetime import datetime, timezone

class EntityManager:
    """
    Manages entity publishing to Lattice platform at standard telemetry rates
    """
    
    def __init__(self, lattice_connector):
        self.lattice_connector = lattice_connector
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        
        # Registered drones
        self.registered_drones: Dict[str, Any] = {}
        
        # Telemetry rates (Hz) - decouple position and status cadences
        # Slightly slower status cadence so it never races location updates
        self.position_update_rate = 3   # 3Hz for smooth arrow and speed/heading
        self.system_status_rate = 0.8   # 0.8Hz (~1.25s)
        
    async def register_drone(self, drone_id: str, drone_state: Any):
        """Register a drone for entity publishing"""
        self.registered_drones[drone_id] = {
            "state": drone_state,
            "last_position_update": datetime.now(timezone.utc),
            "last_status_update": datetime.now(timezone.utc)
        }
        self.logger.info(f"Registered drone {drone_id} for entity publishing")
    
    async def unregister_drone(self, drone_id: str):
        """Unregister a drone from entity publishing"""
        if drone_id in self.registered_drones:
            del self.registered_drones[drone_id]
            self.logger.info(f"Unregistered drone {drone_id} from entity publishing")
    
    async def start_telemetry_publisher(self):
        """Start the telemetry publishing loop"""
        self.is_running = True
        self.logger.info("Starting entity telemetry publisher")
        
        # Run position and status updates concurrently
        await asyncio.gather(
            self._position_update_loop(),
            self._status_update_loop(),
            return_exceptions=True
        )
    
    async def stop(self):
        """Stop the telemetry publisher"""
        self.is_running = False
        self.logger.info("Stopping entity telemetry publisher")
    
    async def _position_update_loop(self):
        """Update drone positions at 4Hz"""
        position_interval = 1.0 / self.position_update_rate  # 250ms
        
        while self.is_running:
            try:
                update_tasks = []
                current_time = datetime.now(timezone.utc)
                
                for drone_id, drone_info in self.registered_drones.items():
                    # Check if it's time to update this drone's position
                    time_since_update = (current_time - drone_info["last_position_update"]).total_seconds()
                    
                    if time_since_update >= position_interval:
                        update_tasks.append(self._update_drone_position(drone_id))
                        drone_info["last_position_update"] = current_time
                
                # Execute all position updates concurrently
                if update_tasks:
                    await asyncio.gather(*update_tasks, return_exceptions=True)
                
                # Sleep until next update cycle
                await asyncio.sleep(position_interval)
                
            except Exception as e:
                self.logger.error(f"Position update loop error: {e}")
                await asyncio.sleep(1)
    
    async def _status_update_loop(self):
        """Update drone system status at 1Hz"""
        status_interval = 1.0 / self.system_status_rate  # 1000ms
        
        while self.is_running:
            try:
                update_tasks = []
                current_time = datetime.now(timezone.utc)
                
                for drone_id, drone_info in self.registered_drones.items():
                    # Check if it's time to update this drone's status
                    time_since_update = (current_time - drone_info["last_status_update"]).total_seconds()
                    
                    if time_since_update >= status_interval:
                        update_tasks.append(self._update_drone_status(drone_id))
                        drone_info["last_status_update"] = current_time
                
                # Execute all status updates concurrently
                if update_tasks:
                    await asyncio.gather(*update_tasks, return_exceptions=True)
                
                # Sleep until next update cycle
                await asyncio.sleep(status_interval)
                
            except Exception as e:
                self.logger.error(f"Status update loop error: {e}")
                await asyncio.sleep(1)
    
    async def _update_drone_position(self, drone_id: str):
        """Update position telemetry for a specific drone"""
        try:
            drone_info = self.registered_drones.get(drone_id)
            if not drone_info:
                return
            
            # Get latest telemetry from drone state
            drone_state = drone_info["state"]
            
            # Build telemetry data for position update using live connector telemetry
            # This ensures we include motion vectors (velocity) for UI movement arrow
            telemetry_live = {}
            try:
                # Import middleware to access connector map indirectly would be circular
                # Instead, expect that middleware queries connectors when publishing (live data is better)
                # Here we prefer to call a live telemetry getter if the state carries a reference
                connector = getattr(drone_state, "_connector", None)
                if connector is not None and hasattr(connector, "get_telemetry"):
                    telemetry_live = await connector.get_telemetry()
            except Exception:
                telemetry_live = {}

            pos = telemetry_live.get("position", {})
            vel_ned = telemetry_live.get("velocity", {})
            heading = telemetry_live.get("heading")
            speed_mps = telemetry_live.get("speed_mps")
            gps_info = telemetry_live.get("gps", {}) if isinstance(telemetry_live, dict) else {}
            gps_fix = gps_info.get("fix_type") if isinstance(gps_info, dict) else None

            telemetry_data = {
                "position": {
                    "lat": pos.get("lat") if pos else (drone_state.position.latitude if hasattr(drone_state, 'position') else 0.0),
                    "lon": pos.get("lon") if pos else (drone_state.position.longitude if hasattr(drone_state, 'position') else 0.0),
                    "alt": pos.get("alt") if pos else (drone_state.position.altitude if hasattr(drone_state, 'position') else 0.0),
                    "absolute_alt": pos.get("absolute_alt") if pos else (drone_state.position.absolute_altitude if hasattr(drone_state, 'position') else 0.0),
                },
                "velocity": {
                    "north": vel_ned.get("north", drone_state.velocity.north if hasattr(drone_state, 'velocity') else 0.0),
                    "east": vel_ned.get("east", drone_state.velocity.east if hasattr(drone_state, 'velocity') else 0.0),
                    "down": vel_ned.get("down", drone_state.velocity.down if hasattr(drone_state, 'velocity') else 0.0),
                },
                "heading": heading if heading is not None else (drone_state.heading if hasattr(drone_state, 'heading') else 0.0),
                "speed_mps": speed_mps if speed_mps is not None else (getattr(drone_state, 'speed_mps', None)),
                "gps": {"fix_type": gps_fix} if gps_fix is not None else {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            # Diagnostics for flicker: log when location becomes valid/invalid transitions
            try:
                lat = telemetry_data["position"]["lat"]
                lon = telemetry_data["position"]["lon"]
                valid = (
                    lat is not None and lon is not None and
                    abs(float(lat)) > 1e-6 and abs(float(lon)) > 1e-6
                )
                if not valid:
                    self.logger.debug(
                        "Telemetry invalid for %s: lat=%s lon=%s gps_fix=%s",
                        drone_id, lat, lon, gps_fix
                    )
            except Exception:
                pass

            # Publish to Lattice
            success = await self.lattice_connector.publish_entity(drone_id, telemetry_data)
            
            if not success:
                self.logger.warning(f"Failed to publish position for drone {drone_id}")
                
        except Exception as e:
            self.logger.error(f"Error updating position for drone {drone_id}: {e}")
    
    async def _update_drone_status(self, drone_id: str):
        """Update system status telemetry for a specific drone"""
        try:
            drone_info = self.registered_drones.get(drone_id)
            if not drone_info:
                return
            
            # Get latest telemetry from drone state
            drone_state = drone_info["state"]

            # ADD THIS DEBUG LOGGING
            self.logger.debug(f"EntityManager reading drone state for {drone_id}:")
            self.logger.debug(f"  current_task: {getattr(drone_state, 'current_task', 'NOT SET')}")
            self.logger.debug(f"  task_status: {getattr(drone_state, 'task_status', 'NOT SET')}")
            self.logger.debug(f"  task_progress: {getattr(drone_state, 'task_progress', 'NOT SET')}")

            # Get live telemetry to include complete snapshot (position, velocity, heading, speed)
            telemetry_live = {}
            try:
                connector = getattr(drone_state, "_connector", None)
                if connector is not None and hasattr(connector, "get_telemetry"):
                    telemetry_live = await connector.get_telemetry()
            except Exception:
                telemetry_live = {}

            pos = telemetry_live.get("position", {}) if isinstance(telemetry_live, dict) else {}
            vel_ned = telemetry_live.get("velocity", {}) if isinstance(telemetry_live, dict) else {}
            heading = telemetry_live.get("heading") if isinstance(telemetry_live, dict) else None
            speed_mps = telemetry_live.get("speed_mps") if isinstance(telemetry_live, dict) else None

            # Build COMPLETE telemetry data for status update
            telemetry_data = {
                "position": {
                    "lat": pos.get("lat") if pos else (drone_state.position.latitude if hasattr(drone_state, 'position') else None),
                    "lon": pos.get("lon") if pos else (drone_state.position.longitude if hasattr(drone_state, 'position') else None),
                    "alt": pos.get("alt") if pos else (drone_state.position.altitude if hasattr(drone_state, 'position') else 0.0),
                    "absolute_alt": pos.get("absolute_alt") if pos else (drone_state.position.absolute_altitude if hasattr(drone_state, 'position') else 0.0),
                },
                "velocity": {
                    "north": vel_ned.get("north", 0.0) if vel_ned else 0.0,
                    "east": vel_ned.get("east", 0.0) if vel_ned else 0.0,
                    "down": vel_ned.get("down", 0.0) if vel_ned else 0.0,
                },
                "heading": heading if heading is not None else (drone_state.heading if hasattr(drone_state, 'heading') else 0.0),
                "speed_mps": speed_mps if speed_mps is not None else 0.0,
                "battery": {
                    "remaining_percent": drone_state.battery_percent if hasattr(drone_state, 'battery_percent') else 100,
                    "voltage": drone_state.battery_voltage if hasattr(drone_state, 'battery_voltage') else 0.0,
                    "current": drone_state.battery_current if hasattr(drone_state, 'battery_current') else 0.0
                },
                "system_status": {
                    "armed": drone_state.armed if hasattr(drone_state, 'armed') else False,
                    "flight_mode": drone_state.flight_mode if hasattr(drone_state, 'flight_mode') else "UNKNOWN",
                    "status": drone_state.status if hasattr(drone_state, 'status') else "DISCONNECTED",
                },
                "task_info": {
                    "current_task": drone_state.current_task,
                    "task_status": drone_state.task_status,
                    "task_progress": drone_state.task_progress if hasattr(drone_state, 'task_progress') else 0.0
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # RIGHT BEFORE publish_entity, reduce verbosity to DEBUG
            self.logger.debug(f"EntityManager publishing status: task={telemetry_data.get('task_info')}")

            # Publish to Lattice
            success = await self.lattice_connector.publish_entity(drone_id, telemetry_data)
            
            if not success:
                self.logger.warning(f"Failed to publish status for drone {drone_id}")
                
        except Exception as e:
            self.logger.error(f"Error updating status for drone {drone_id}: {e}")
    
    async def publish_alert(self, drone_id: str, alert_type: str, alert_data: Dict[str, Any]):
        """Publish high-priority alert immediately"""
        try:
            telemetry_data = {
                "alert": {
                    "type": alert_type,
                    "severity": alert_data.get("severity", "WARNING"),
                    "message": alert_data.get("message", ""),
                    "data": alert_data
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Publish immediately
            success = await self.lattice_connector.publish_entity(drone_id, telemetry_data)
            
            if success:
                self.logger.info(f"Published {alert_type} alert for drone {drone_id}")
            else:
                self.logger.error(f"Failed to publish {alert_type} alert for drone {drone_id}")
                
        except Exception as e:
            self.logger.error(f"Error publishing alert for drone {drone_id}: {e}") 