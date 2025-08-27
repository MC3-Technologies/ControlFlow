"""
MAVLink/MAVSDK connector for drone flight control
"""

import asyncio
import logging
import re
from typing import Optional, Dict, Any
from mavsdk import System
from mavsdk.offboard import PositionNedYaw, VelocityBodyYawspeed
from mavsdk.action import ActionError
from mavsdk.telemetry import LandedState, FlightMode

class MAVSDKConnector:
    """
    Connector for drone flight control using MAVSDK-Python
    Supports both SITL and real hardware connections
    """
    
    def __init__(self, drone_config):
        self.config = drone_config
        self.logger = logging.getLogger(f"MAVSDK-{drone_config.id}")
        
        # Determine MAVSDK server port based on drone connection
        # Extract port from connection string (e.g., "udp://:14550" -> 14550)
        import re
        port_match = re.search(r':(\d+)', drone_config.connection_string)
        if port_match:
            udp_port = int(port_match.group(1))
            # Map UDP port to MAVSDK server port (offset by 35500)
            # 14540 -> 50040, 14550 -> 50050, etc.
            mavsdk_port = 50040 + (udp_port - 14540)
        else:
            mavsdk_port = 50051  # Default for single drone setup
        
        # Create System with server address
        self.system = System(mavsdk_server_address="127.0.0.1", port=mavsdk_port)
        self.is_connected = False
        self.is_armed = False
        
        # Connection string (e.g., "udp://:14540" for SITL)
        self.connection_string = drone_config.connection_string
        # Cache last good kinematics to smooth intermittent streams
        self._last_heading_deg: Optional[float] = None
        self._last_speed_mps: Optional[float] = None
        self._last_velocity_ned: Optional[Dict[str, float]] = None
        # Smoothed values to minimize UI flicker
        self._smoothed_heading_deg: Optional[float] = None
        self._smoothed_speed_mps: Optional[float] = None
        self._smoothed_velocity_ned: Optional[Dict[str, float]] = None
        # Low-pass filter coefficient (0..1). Higher = more responsive, lower = smoother
        # Use stronger smoothing by default to eliminate UI flicker; override via env TELEMETRY_SMOOTH_ALPHA
        try:
            import os as _os
            self._smooth_alpha = float(_os.getenv("TELEMETRY_SMOOTH_ALPHA", "0.2"))
        except Exception:
            self._smooth_alpha: float = 0.2
        
    async def connect(self):
        """Connect to the drone via MAVLink"""
        try:
            self.logger.info(f"Connecting to drone at {self.connection_string} via MAVSDK server")
            
            # Connect through the MAVSDK server
            await self.system.connect()
            
            # Wait for connection
            async for state in self.system.core.connection_state():
                if state.is_connected:
                    self.is_connected = True
                    self.logger.info(f"Connected to drone {self.config.id}")
                    break
            
            # Wait for drone to have a global position estimate
            async for health in self.system.telemetry.health():
                if health.is_global_position_ok and health.is_home_position_ok:
                    self.logger.info(f"Drone {self.config.id} has global position")
                    break
            
            # Increase telemetry rates to keep UI motion responsive
            try:
                await self.system.telemetry.set_rate_position(5.0)
            except Exception:
                pass
            try:
                await self.system.telemetry.set_rate_velocity_ned(5.0)
            except Exception:
                pass
            try:
                await self.system.telemetry.set_rate_attitude_euler(5.0)
            except Exception:
                pass
            try:
                await self.system.telemetry.set_rate_gps_info(1.0)
            except Exception:
                pass

        except Exception as e:
            self.logger.error(f"Failed to connect to drone: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from the drone"""
        if self.is_connected:
            try:
                # Note: ArduPilot automatically disarms after landing, so no manual disarm needed
                self.is_connected = False
                self.logger.info(f"Disconnected from drone {self.config.id}")
            except Exception as e:
                self.logger.error(f"Error disconnecting from drone: {e}")
    
    async def reconnect(self):
        """Attempt to reconnect to the drone"""
        await self.disconnect()
        await asyncio.sleep(2)
        await self.connect()
    
    async def arm(self) -> bool:
        """Arm the drone"""
        try:
            # Ensure pre-arm health
            try:
                async for health in self.system.telemetry.health():
                    # Minimal checks; do not block forever
                    break
            except Exception:
                pass
            await self.system.action.arm()
            self.is_armed = True
            self.logger.info(f"Armed drone {self.config.id}")
            return True
        except ActionError as e:
            self.logger.error(f"Failed to arm drone: {e}")
            return False
    
    async def disarm(self) -> bool:
        """Disarm the drone"""
        try:
            await self.system.action.disarm()
            self.is_armed = False
            self.logger.info(f"Disarmed drone {self.config.id}")
            return True
        except ActionError as e:
            # If the drone is already disarmed, treat this as success to keep the
            # shutdown sequence idempotent.  MAVSDK raises ActionError with the
            # generic message "FAILED: 'Failed'" when ArduPilot responds
            # COMMAND_ACK with a failure because it is already disarmed.
            try:
                async for armed_state in self.system.telemetry.armed():
                    if not armed_state:
                        self.logger.debug(
                            f"Disarm command returned error but vehicle is already disarmed"
                        )
                        self.is_armed = False
                        return True
                    break
            except Exception:
                # Telemetry unavailable; fall through to failure handling
                pass

            self.logger.error(f"Failed to disarm drone: {e}")
            return False
    
    async def takeoff(self, altitude: float = 10.0) -> bool:
        """
        Takeoff to specified altitude
        
        Args:
            altitude: Target altitude in meters AGL
            
        Returns:
            True if takeoff successful, False otherwise
        """
        try:
            # Arm the drone first
            if not self.is_armed:
                if not await self.arm():
                    return False
            
            # Small delay to allow EKF/mode to settle after arming
            await asyncio.sleep(1.5)

            # Set takeoff altitude
            await self.system.action.set_takeoff_altitude(altitude)

            async def _attempt_takeoff() -> bool:
                try:
                    await self.system.action.takeoff()
                except ActionError as ae:
                    self.logger.error(f"Takeoff command rejected: {ae}")
                    return False

                # Wait for IN_AIR and climb
                # First, wait up to 10s for mode to switch away from HOLD and/or to TAKEOFF
                mode_wait = 0
                async for fm in self.system.telemetry.flight_mode():
                    if fm == FlightMode.TAKEOFF:
                        break
                    mode_wait += 1
                    if mode_wait >= 10:
                        break
                    await asyncio.sleep(1)

                # Then wait to reach target altitude with timeout
                timeout_counter = 0
                max_timeout = 60  # seconds
                async for position in self.system.telemetry.position():
                    if position.relative_altitude_m >= altitude * 0.95:
                        self.logger.info(f"Takeoff complete at {position.relative_altitude_m:.1f}m")
                        return True
                    timeout_counter += 1
                    if timeout_counter > max_timeout:
                        self.logger.warning(
                            f"Takeoff timeout - current altitude: {position.relative_altitude_m:.1f}m"
                        )
                        return False
                    await asyncio.sleep(1)
                return False

            # First attempt
            ok = await _attempt_takeoff()
            if ok:
                return True

            # Retry once after short backoff (common if EKF yaw alignment not ready)
            self.logger.info("Retrying takeoff in 2s")
            await asyncio.sleep(2)
            ok = await _attempt_takeoff()
            if ok:
                return True

            # Fallback: command a guided climb to current lat/lon at requested AGL
            try:
                telemetry = await self.get_telemetry()
                pos = telemetry.get("position", {})
                lat = float(pos.get("lat"))
                lon = float(pos.get("lon"))
                abs_alt = float(pos.get("absolute_alt"))
                target_amsl = abs_alt + float(altitude)
                self.logger.info(
                    f"Fallback goto_location to AMSL {target_amsl:.1f} (lat={lat:.6f}, lon={lon:.6f})"
                )
                await self.system.action.goto_location(lat, lon, target_amsl, 0)

                # Wait to reach target relative altitude
                timeout_counter = 0
                max_timeout = 60
                async for position in self.system.telemetry.position():
                    if position.relative_altitude_m >= altitude * 0.90:
                        self.logger.info(
                            f"Guided climb reached {position.relative_altitude_m:.1f}m (target {altitude}m)"
                        )
                        return True
                    timeout_counter += 1
                    if timeout_counter > max_timeout:
                        self.logger.warning(
                            f"Guided climb timeout - current altitude: {position.relative_altitude_m:.1f}m"
                        )
                        break
                    await asyncio.sleep(1)
            except Exception as fb_exc:
                self.logger.error(f"Fallback guided climb failed: {fb_exc}")

            return False

        except Exception as e:
            self.logger.error(f"Takeoff failed: {e}")
            return False
    
    async def land(self) -> bool:
        """Land the drone"""
        try:
            await self.system.action.land()
            
            # Wait for landing to complete with timeout
            timeout_counter = 0
            max_timeout = 60  # 60 seconds timeout
            
            async for landed_state in self.system.telemetry.landed_state():
                if landed_state == LandedState.ON_GROUND:
                    self.logger.info(f"Landing complete")
                    return True
                
                timeout_counter += 1
                if timeout_counter > max_timeout:
                    self.logger.warning("Landing timeout")
                    return False
                
                await asyncio.sleep(1)
            
            # If we exit the loop without landing, return False
            return False
            
        except Exception as e:
            self.logger.error(f"Landing failed: {e}")
            return False
    
    async def goto_position(self, lat: float, lon: float, alt: float) -> bool:
        """
        Fly to specified GPS position
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees  
            alt: Altitude in meters AGL
            
        Returns:
            True if position reached, False otherwise
        """
        try:
            # Convert requested AGL to absolute altitude expected by goto_location
            try:
                async for pos in self.system.telemetry.position():
                    current_rel = float(getattr(pos, "relative_altitude_m", 0.0))
                    current_abs = float(getattr(pos, "absolute_altitude_m", 0.0))
                    alt_abs_target = current_abs - current_rel + float(alt)
                    break
            except Exception:
                alt_abs_target = float(alt)

            await self.system.action.goto_location(lat, lon, alt_abs_target, 0)  # 0 yaw
            
            # Wait for drone to reach position (within tolerance)
            target_reached = False
            tolerance = 2.0  # meters
            
            async for position in self.system.telemetry.position():
                # Calculate distance to target
                distance = self._calculate_distance(
                    position.latitude_deg, position.longitude_deg,
                    lat, lon
                )
                
                # Compare current rel altitude to requested AGL
                alt_diff = abs(position.relative_altitude_m - float(alt))
                
                if distance < tolerance and alt_diff < tolerance:
                    self.logger.info(f"Reached target position")
                    target_reached = True
                    break
            
            return target_reached
            
        except Exception as e:
            self.logger.error(f"Failed to go to position: {e}")
            return False
    
    async def hold_position(self):
        """Hold current position"""
        try:
            await self.system.action.hold()
            self.logger.info("Holding position")
        except Exception as e:
            self.logger.error(f"Failed to hold position: {e}")
    
    async def return_to_launch(self) -> bool:
        """Return to launch position"""
        try:
            await self.system.action.return_to_launch()
            self.logger.info("Returning to launch")
            return True
        except Exception as e:
            self.logger.error(f"Failed to return to launch: {e}")
            return False
    
    async def get_telemetry(self) -> Dict[str, Any]:
        """Get current telemetry data"""
        try:
            # Get latest telemetry (non-blocking)
            position = None
            battery = None
            armed = None
            gps_fix_type = None
            velocity_ned = None
            heading_deg = None
            
            # Use async iteration with timeout to get latest values
            async for pos in self.system.telemetry.position():
                # Some stacks may transiently emit 0/0 before GPS is ready; filter these
                lat_val = float(getattr(pos, "latitude_deg", 0.0))
                lon_val = float(getattr(pos, "longitude_deg", 0.0))
                abs_ok = abs(lat_val) > 1e-6 and abs(lon_val) > 1e-6
                # Cache last-known-good valid position to keep the UI continuous
                if abs_ok:
                    self._last_valid_position = {  # type: ignore[attr-defined]
                        "lat": lat_val,
                        "lon": lon_val,
                        "alt": float(getattr(pos, "relative_altitude_m", 0.0)),
                        "absolute_alt": float(getattr(pos, "absolute_altitude_m", 0.0)),
                    }
                # Prefer current valid position; else fallback to last-good
                if abs_ok:
                    position = {
                        "lat": lat_val,
                        "lon": lon_val,
                        "alt": float(getattr(pos, "relative_altitude_m", 0.0)),
                        "absolute_alt": float(getattr(pos, "absolute_altitude_m", 0.0)),
                    }
                else:
                    position = getattr(self, "_last_valid_position", None)
                break
            
            async for bat in self.system.telemetry.battery():
                # MAVSDK returns remaining_percent in range 0.0–1.0. Convert to human-readable 0–100 %.
                remaining = bat.remaining_percent
                if remaining is not None and remaining <= 1.0:
                    remaining *= 100.0
                battery = {
                    "remaining_percent": remaining,
                    "voltage": bat.voltage_v
                }
                break
            
            async for arm_state in self.system.telemetry.armed():
                armed = arm_state
                break

            # Fetch GPS fix type (needed for pre-flight checks)
            try:
                async for gps in self.system.telemetry.gps_info():
                    # gps.fix_type is an Enum; converting via getattr to satisfy type checker
                    fix_val = getattr(gps, "fix_type", None)
                    gps_fix_type = int(getattr(fix_val, "value", fix_val)) if fix_val is not None else None  # type: ignore[arg-type]
                    break
            except Exception:
                # Not all firmware streams gps_info; leave as None
                pass

            # Fetch velocity (NED) if available
            try:
                async for vel in self.system.telemetry.velocity_ned():
                    # MAVSDK VelocityNed has north_m_s, east_m_s, down_m_s
                    velocity_ned = {
                        "north": float(getattr(vel, "north_m_s", 0.0)),
                        "east": float(getattr(vel, "east_m_s", 0.0)),
                        "down": float(getattr(vel, "down_m_s", 0.0)),
                    }
                    self._last_velocity_ned = velocity_ned
                    break
            except Exception:
                # Optional stream
                pass

            # Fetch heading (from attitude euler yaw) if available
            try:
                async for att in self.system.telemetry.attitude_euler():
                    # yaw_deg in range [-180, 180]; normalize to [0, 360)
                    yaw = float(getattr(att, "yaw_deg", 0.0))
                    heading = (yaw + 360.0) % 360.0
                    heading_deg = heading
                    self._last_heading_deg = heading_deg
                    break
            except Exception:
                # Optional stream
                pass
            
            # Compute speed magnitude from velocity if available
            try:
                v_raw = velocity_ned or self._last_velocity_ned or {"north": 0.0, "east": 0.0, "down": 0.0}
                speed_raw = float((v_raw["north"] ** 2 + v_raw["east"] ** 2 + v_raw["down"] ** 2) ** 0.5)
                self._last_speed_mps = speed_raw
            except Exception:
                speed_raw = self._last_speed_mps if self._last_speed_mps is not None else 0.0

            # Exponential smoothing for velocity and speed
            try:
                alpha = self._smooth_alpha
                # Velocity components
                v_prev = self._smoothed_velocity_ned or self._last_velocity_ned or {"north": 0.0, "east": 0.0, "down": 0.0}
                v_curr = velocity_ned or self._last_velocity_ned or v_prev
                v_smooth = {
                    "north": float(alpha * v_curr.get("north", 0.0) + (1.0 - alpha) * v_prev.get("north", 0.0)),
                    "east": float(alpha * v_curr.get("east", 0.0) + (1.0 - alpha) * v_prev.get("east", 0.0)),
                    "down": float(alpha * v_curr.get("down", 0.0) + (1.0 - alpha) * v_prev.get("down", 0.0)),
                }
                self._smoothed_velocity_ned = v_smooth
                # Speed scalar
                sp_prev = self._smoothed_speed_mps if self._smoothed_speed_mps is not None else speed_raw
                sp_smooth = float(alpha * (speed_raw or 0.0) + (1.0 - alpha) * (sp_prev or 0.0))
                # Apply a deadband to avoid tiny oscillations at near-zero speeds
                if abs(sp_smooth) < 0.15:
                    sp_smooth = 0.0
                self._smoothed_speed_mps = sp_smooth
            except Exception:
                v_smooth = velocity_ned or self._last_velocity_ned
                sp_smooth = speed_raw

            # Fill missing heading with last good to avoid UI flicker
            if heading_deg is None and self._last_heading_deg is not None:
                heading_deg = self._last_heading_deg

            # Exponential smoothing for heading (handle wrap-around)
            try:
                if heading_deg is not None:
                    if self._smoothed_heading_deg is None:
                        self._smoothed_heading_deg = heading_deg
                    else:
                        prev = self._smoothed_heading_deg
                        # Smallest signed angular difference
                        delta = ((heading_deg - prev + 180.0) % 360.0) - 180.0
                        # Stronger smoothing for heading to remove twitch
                        self._smoothed_heading_deg = (prev + self._smooth_alpha * 0.7 * delta) % 360.0
                heading_out = self._smoothed_heading_deg if self._smoothed_heading_deg is not None else heading_deg
            except Exception:
                heading_out = heading_deg

            return {
                "position": position,
                "battery": battery,
                "armed": armed,
                "velocity": v_smooth or velocity_ned or self._last_velocity_ned,
                "speed_mps": sp_smooth,
                "heading": heading_out,
                "gps": {"fix_type": gps_fix_type} if gps_fix_type is not None else {},
                "timestamp": asyncio.get_event_loop().time()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get telemetry: {e}")
            return {}
    
    async def get_position(self) -> Optional[Dict[str, float]]:
        """Get current position"""
        telemetry = await self.get_telemetry()
        return telemetry.get("position")
    
    # async def trigger_camera(self) -> bool:
    #     """
    #     Trigger camera capture
        
    #     Returns:
    #         True if camera triggered successfully, False otherwise
    #     """
    #     try:
    #         # Check if camera plugin is available
    #         if hasattr(self.system, 'camera'):
    #             # Modern MAVSDK Python uses camera.take_photo() without args; older versions accept (component_id)
    #             cam = self.system.camera
    #             try:
    #                 await cam.take_photo(component_id=1)
    #             except TypeError:
    #                 await cam.take_photo(1)
    #             self.logger.debug(f"Camera triggered on {self.config.id}")
    #             return True
    #         else:
    #             # Fallback: Use action command to trigger camera servo
    #             # This would trigger a servo connected to the camera shutter
    #             self.logger.warning("Camera plugin not available, using servo trigger")
    #             # In real implementation, you'd send MAV_CMD_DO_SET_SERVO
    #             return False
                
    #     except Exception as e:
    #         self.logger.warning(f"Camera trigger failed: {e}")
    #         return False
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two GPS coordinates in meters"""
        import math
        
        R = 6371000  # Earth radius in meters
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat/2) * math.sin(delta_lat/2) +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon/2) * math.sin(delta_lon/2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c 