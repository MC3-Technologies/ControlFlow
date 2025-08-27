"""
Drone state and configuration models
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum

class DroneStatus(Enum):
    """Drone connection status"""
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"
    ARMED = "ARMED"
    IN_FLIGHT = "IN_FLIGHT"

class TaskStatus(Enum):
    """Task execution status"""
    NONE = "NONE"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"

@dataclass
class Position:
    """GPS position data"""
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0  # meters AGL
    absolute_altitude: float = 0.0  # meters MSL

@dataclass
class Velocity:
    """Velocity data in NED frame"""
    north: float = 0.0  # m/s
    east: float = 0.0   # m/s
    down: float = 0.0   # m/s

@dataclass
class Battery:
    """Battery status data"""
    remaining_percent: float = 100.0
    voltage: float = 0.0  # volts
    current: float = 0.0  # amps
    capacity: float = 0.0  # mAh

@dataclass
class SystemHealth:
    """System health indicators"""
    gps_fix: bool = False
    gps_satellites: int = 0
    imu_ok: bool = False
    mag_ok: bool = False
    baro_ok: bool = False
    rc_ok: bool = False
    failsafe_active: bool = False

@dataclass
class DroneState:
    """Complete drone state information"""
    # Identification
    drone_id: str
    connection_string: str
    
    # Status
    status: str = DroneStatus.DISCONNECTED.value
    armed: bool = False
    flight_mode: str = "UNKNOWN"
    
    # Position and motion
    position: Position = field(default_factory=Position)
    velocity: Velocity = field(default_factory=Velocity)
    heading: float = 0.0  # degrees (0-360)
    
    # Battery
    battery_percent: float = 100.0
    battery_voltage: float = 0.0
    battery_current: float = 0.0
    
    # System health
    system_health: SystemHealth = field(default_factory=SystemHealth)
    
    # Task information
    current_task: Optional[str] = None
    task_status: str = TaskStatus.NONE.value
    task_progress: float = 0.0
    
    # Metadata
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    connected_since: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary"""
        return {
            "drone_id": self.drone_id,
            "connection_string": self.connection_string,
            "status": self.status,
            "armed": self.armed,
            "flight_mode": self.flight_mode,
            "position": {
                "lat": self.position.latitude,
                "lon": self.position.longitude,
                "alt": self.position.altitude,
                "abs_alt": self.position.absolute_altitude
            },
            "velocity": {
                "north": self.velocity.north,
                "east": self.velocity.east,
                "down": self.velocity.down
            },
            "heading": self.heading,
            "battery": {
                "percent": self.battery_percent,
                "voltage": self.battery_voltage,
                "current": self.battery_current
            },
            "health": {
                "gps_fix": self.system_health.gps_fix,
                "gps_satellites": self.system_health.gps_satellites,
                "imu_ok": self.system_health.imu_ok,
                "mag_ok": self.system_health.mag_ok,
                "baro_ok": self.system_health.baro_ok,
                "rc_ok": self.system_health.rc_ok,
                "failsafe": self.system_health.failsafe_active
            },
            "task": {
                "current": self.current_task,
                "status": self.task_status,
                "progress": self.task_progress
            },
            "last_update": self.last_update.isoformat(),
            "connected_since": self.connected_since.isoformat() if self.connected_since else None
        }

@dataclass
class DroneConfig:
    """Drone configuration"""
    id: str
    connection_string: str
    type: str = "quadcopter"
    manufacturer: str = "CubePilot"
    model: str = "CubeOrange"
    capabilities: list = field(default_factory=lambda: ["mapping", "relay", "dropping"])
    max_altitude: float = 120.0  # meters AGL (FAA limit)
    max_speed: float = 20.0  # m/s
    max_flight_time: int = 1800  # seconds (30 minutes)
    geofence_enabled: bool = True
    rtl_altitude: float = 50.0  # Return to launch altitude
    failsafe_action: str = "RTL"  # RTL, LAND, or LOITER 