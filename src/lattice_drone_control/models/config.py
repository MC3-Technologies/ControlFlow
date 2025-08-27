"""
Configuration models for the middleware system
"""

from dataclasses import dataclass, field
import os
from typing import List, Dict, Any, Optional


# Import DroneConfig
from .drone import DroneConfig

@dataclass
class LatticeConfig:
    """Lattice platform configuration"""
    # NOTE: Replace with actual Lattice endpoint provided by Anduril
    url: str = os.getenv("LATTICE_URL", "lattice.anduril.com")
    bearer_token: Optional[str] = None
    # Whether to use gRPC instead of REST (SDK v2 is REST-first)
    use_grpc: bool = False
    timeout: int = 30
    retry_attempts: int = 3
    verify_ssl: bool = True

@dataclass
class MiddlewareConfig:
    """Main middleware configuration"""
    # Service configuration
    service_name: str = "lattice-drone-middleware"
    environment: str = "development"  # development, staging, production
    log_level: str = "INFO"
    
    # Mock mode flag - set to True to run without Lattice connection
    mock_mode: bool = False
    
    # Lattice configuration (optional when mock_mode is True)
    lattice: Optional[LatticeConfig] = None
    
    # Drone configurations
    drones: List[DroneConfig] = field(default_factory=list)
    
    # Health monitoring
    health_check_interval: int = 10  # seconds
    telemetry_timeout: int = 30  # seconds
    
    # Performance tuning
    max_concurrent_tasks: int = 10
    task_queue_size: int = 100
    
    # Network configuration
    grpc_max_message_size: int = 10 * 1024 * 1024  # 10MB
    http_timeout: int = 60  # seconds
    
    # Safety configuration
    min_battery_percent: float = 20.0
    max_wind_speed: float = 15.0  # m/s
    geofence_radius: float = 500.0  # meters
    emergency_rtl_altitude: float = 100.0  # meters
    
    # Telemetry rates (Hz)
    position_update_rate: float = 4.0  # 4Hz
    status_update_rate: float = 1.0   # 1Hz
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MiddlewareConfig':
        """Create config from dictionary"""
        
        # Extract Lattice config (optional in mock mode)
        lattice_data = data.get('lattice', {})
        if lattice_data:
            # Substitute environment placeholders in URL if present
            if 'url' in lattice_data:
                url_value = lattice_data['url']
                if isinstance(url_value, str) and url_value.startswith('${') and url_value.endswith('}'):
                    env_var_name = url_value[2:-1]
                    lattice_data['url'] = os.getenv(env_var_name, lattice_data['url'])

            # Handle environment variable substitution for bearer_token
            if 'bearer_token' in lattice_data:
                token_value = lattice_data['bearer_token']
                if isinstance(token_value, str) and token_value.startswith('${') and token_value.endswith('}'):
                    # Extract environment variable name
                    env_var_name = token_value[2:-1]
                    # Get from environment
                    lattice_data['bearer_token'] = os.getenv(env_var_name)
                    if not lattice_data['bearer_token']:
                        # Try common alternative environment variable names for compatibility
                        for alt_name in ['ENVIRONMENT_TOKEN', 'LATTICE_BEARER_TOKEN', 'LATTICE_TOKEN', 'ANDURIL_BEARER_TOKEN']:
                            lattice_data['bearer_token'] = os.getenv(alt_name)
                            if lattice_data['bearer_token']:
                                break
            
            lattice_config = LatticeConfig(**lattice_data)
        else:
            lattice_config = None
        
        # Extract drone configs
        drones_data = data.get('drones', [])
        drone_configs = [DroneConfig(**drone) for drone in drones_data]
        
        # Remove nested configs from data
        config_data = data.copy()
        config_data.pop('lattice', None)
        config_data.pop('drones', None)
        
        return cls(
            lattice=lattice_config,
            drones=drone_configs,
            **config_data
        )

@dataclass
class TaskConfig:
    """Task-specific configuration"""
    task_type: str
    enabled: bool = True
    timeout: int = 3600  # seconds (1 hour default)
    max_retries: int = 2
    
    # Task-specific parameters
    parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MappingTaskConfig(TaskConfig):
    """Configuration for mapping tasks"""
    def __init__(self):
        super().__init__(
            task_type="mapping",
            parameters={
                "default_altitude": 50.0,  # meters
                "default_overlap": 0.8,    # 80%
                "camera_fov": 30.0,        # meters ground coverage
                "photo_interval": 2.0,      # seconds
                "max_area_size": 10000.0   # square meters
            }
        )

@dataclass
class RelayTaskConfig(TaskConfig):
    """Configuration for relay tasks"""
    def __init__(self):
        super().__init__(
            task_type="relay",
            parameters={
                "default_altitude": 100.0,     # meters
                "position_tolerance": 5.0,     # meters
                "update_interval": 5.0,        # seconds
                "max_duration": 1800          # seconds (30 minutes)
            }
        )

@dataclass
class DroppingTaskConfig(TaskConfig):
    """Configuration for dropping tasks"""
    def __init__(self):
        super().__init__(
            task_type="dropping",
            parameters={
                "approach_altitude": 50.0,    # meters
                "drop_altitude": 10.0,        # meters
                "position_tolerance": 1.0,    # meters
                "stabilization_time": 3.0,    # seconds
                "max_drops_per_flight": 5,
                "servo_channel": 7,           # Servo channel for release
                "release_pwm": 1900,          # PWM value for release
                "hold_pwm": 1100             # PWM value for hold
            }
        ) 