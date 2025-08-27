# pyright: reportAssignmentType=false

"""
Lattice platform connector aligned to Lattice SDK v2 REST API.
Uses the high-level `anduril` client like the official sample apps.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Dict, List, Callable, cast
import uuid
import ssl
import certifi
import traceback
import sys
from pathlib import Path

# gRPC imports
try:
    from grpclib.client import Channel as GrpcChannel
    from grpclib.exceptions import GRPCError
    GRPC_AVAILABLE = True
except ImportError:
    GrpcChannel = None  # type: ignore
    GRPCError = Exception
    GRPC_AVAILABLE = False

# Try to import REST Lattice SDK (v2), prefer local SDK if present
REST_SDK_AVAILABLE = False
anduril = None  # type: ignore

def _ensure_local_anduril_on_path() -> None:
    try:
        here = Path(__file__).resolve()
        # Walk up to 6 levels to find 'lattice-sdk-python/src/anduril/__init__.py'
        for parent in [here.parent] + list(here.parents):
            candidate = parent / "lattice-sdk-python" / "src" / "anduril" / "__init__.py"
            if candidate.is_file():
                sdk_src = candidate.parent.parent  # path to '.../lattice-sdk-python/src'
                if str(sdk_src) not in sys.path:
                    sys.path.insert(0, str(sdk_src))
                return
    except Exception:
        return

_ensure_local_anduril_on_path()
try:
    import anduril  # type: ignore
    REST_SDK_AVAILABLE = True
except Exception:
    anduril = None  # type: ignore
    REST_SDK_AVAILABLE = False

# Try to import Lattice SDK
# NOTE: The linter may show errors here because it doesn't have access to the
# proprietary Lattice SDK. These are false positives that will resolve when
# the actual SDK is installed.
LATTICE_SDK_AVAILABLE = False
try:
    # Import actual Lattice SDK - contact Anduril for access
    from anduril.entitymanager.v1 import (  # type: ignore
        EntityManagerApiStub,
        PublishEntityRequest,
        GetEntityRequest,
        Entity,
        Aliases,
        Location,
        Position,
        Ontology,
        Template,
        Provenance,
        MilView,
    )
    # Attempt to import TaskCatalog and TaskDefinition from proper location
    try:
        from anduril.tasks.v2 import TaskCatalog, TaskDefinition  # type: ignore
    except ImportError:
        try:
            # Fallback for older SDK layouts where these lived in entitymanager.v1
            from anduril.entitymanager.v1 import TaskCatalog, TaskDefinition  # type: ignore
        except ImportError:
            TaskCatalog = None  # type: ignore
            TaskDefinition = None  # type: ignore

    from anduril.taskmanager.v1 import (  # type: ignore
        TaskManagerApiStub, 
        ListenAsAgentRequest, 
        UpdateStatusRequest,
        QueryTasksRequest,
        TaskStatus  # TaskStatus is in taskmanager.v1
    )
    from anduril.ontology.v1 import (  # type: ignore
        Disposition, 
        Environment
    )
    
    LATTICE_SDK_AVAILABLE = True

    # Ensure TaskCatalog / TaskDefinition are available even if this SDK build
    # does not expose them (older versions)
    if 'TaskCatalog' not in globals() or TaskCatalog is None:  # type: ignore
        class TaskCatalog:  # type: ignore
            def __init__(self, task_definitions=None):
                self.task_definitions = task_definitions or []

        class TaskDefinition:  # type: ignore
            def __init__(self, task_type=None, specification_url=None, **kwargs):
                self.task_type = task_type or ""
                self.specification_url = specification_url or ""

        logging.getLogger(__name__).warning(
            "SDK version lacks TaskCatalog/TaskDefinition – using fallback stubs"
        )
    
    # When real SDK is available, we need to create our status constants
    # as the real TaskStatus is a protobuf message, not constants
    class TaskStatusConstants:
        """Task status constants that match Anduril Lattice API specification"""
        # Correct Anduril Lattice API status constants as per official documentation
        STATUS_SENT = "STATUS_SENT"
        STATUS_MACHINE_RECEIPT = "STATUS_MACHINE_RECEIPT"
        STATUS_ACK = "STATUS_ACK"
        STATUS_WILCO = "STATUS_WILCO"
        STATUS_EXECUTING = "STATUS_EXECUTING"
        STATUS_DONE_OK = "STATUS_DONE_OK"
        STATUS_DONE_NOT_OK = "STATUS_DONE_NOT_OK"
        
        # Legacy aliases for backward compatibility
        ACCEPTED = "STATUS_ACK"
        IN_PROGRESS = "STATUS_EXECUTING"
        COMPLETED = "STATUS_DONE_OK"
        FAILED = "STATUS_DONE_NOT_OK"
        CANCELLED = "STATUS_DONE_NOT_OK"
    
    # Create a safe wrapper to avoid overriding the actual SDK TaskStatus
    # This prevents conflicts between real SDK imports and our constants
    _TaskStatusValues = TaskStatusConstants
    
    # Export the constants through a module-level variable that won't conflict
    # with SDK imports but can still be imported by other modules
    TASK_STATUS = TaskStatusConstants()
    
    # TaskCatalog and TaskDefinition should come from the real SDK imports
    # For development, we'll skip TaskCatalog when real SDK doesn't provide it
    
except ImportError:
    # Fallback for development/testing when SDK is not available
    logging.warning("Lattice SDK not available, using mock implementation")
    
    # Mock classes that mimic the SDK structure
    class EntityManagerApiStub:
        def __init__(self, channel):
            self.channel = channel
            
        async def publish_entity(self, request, metadata=None):
            # Mock response
            return type('Response', (), {'success': True})()
    
    class TaskManagerApiStub:
        def __init__(self, channel):
            self.channel = channel
            self._running = False
            
        async def listen_as_agent(self, request, metadata=None):
            # Mock async generator that simulates a long-running task stream
            # Must return an actual async generator, not a coroutine
            self._running = True
            while self._running:
                # Wait indefinitely for tasks (none will come in mock mode)
                await asyncio.sleep(30)  # Longer sleep to reduce log spam
                # Never yield anything in mock mode, just keep the connection "alive"
                # This prevents the TaskManager from thinking the connection died
                if False:  # This will never execute but makes it a generator
                    yield None
        
        async def update_status(self, request, metadata=None):
            # Mock response with debug logging
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"=== MOCK update_status called ===")
            logger.debug(f"Request type: {type(request)}")
            logger.debug(f"Request attributes: {dir(request)}")
            if hasattr(request, '__dict__'):
                logger.debug(f"Request dict: {request.__dict__}")
            logger.debug(f"Metadata: {metadata}")
            
            # Mock successful response
            response = type('Response', (), {'success': True, 'error': None})()
            logger.debug(f"Returning mock response: success=True, error=None")
            return response
            
        async def query_tasks(self, request, metadata=None):
            # Mock response
            return type('Response', (), {'tasks': []})()
    
    # Mock proto classes
    class PublishEntityRequest:
        def __init__(self, entity=None): 
            self.entity = entity
    
    class Entity:
        def __init__(self, **kwargs): 
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    class Position:
        def __init__(self, latitude_degrees=0, longitude_degrees=0, altitude_hae_meters=0):
            self.latitude_degrees = latitude_degrees
            self.longitude_degrees = longitude_degrees
            self.altitude_hae_meters = altitude_hae_meters
            
    class Location:
        def __init__(self, position=None):
            self.position = position
            
    class Aliases:
        def __init__(self, name=""):
            self.name = name
        
    class Ontology:
        def __init__(self, template=None, platform_type=""):
            self.template = template
            self.platform_type = platform_type
            
    class Provenance:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
                
    class MilView:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        
    class Template:
        ASSET = "TEMPLATE_ASSET"
        TRACK = "TEMPLATE_TRACK"
    
    class Disposition:
        FRIENDLY = "DISPOSITION_FRIENDLY"
        HOSTILE = "DISPOSITION_HOSTILE"
        NEUTRAL = "DISPOSITION_NEUTRAL"
        SUSPICIOUS = "DISPOSITION_SUSPICIOUS"
        
    class Environment:
        AIR = "ENVIRONMENT_AIR"
        SURFACE = "ENVIRONMENT_SURFACE"
        LAND = "ENVIRONMENT_LAND"
    
    class TaskStatus:
        """Mock task status constants for development without SDK"""
        # Correct Anduril Lattice API status constants as per official documentation
        STATUS_SENT = "STATUS_SENT"
        STATUS_MACHINE_RECEIPT = "STATUS_MACHINE_RECEIPT"
        STATUS_ACK = "STATUS_ACK"
        STATUS_WILCO = "STATUS_WILCO"
        STATUS_EXECUTING = "STATUS_EXECUTING"
        STATUS_DONE_OK = "STATUS_DONE_OK"
        STATUS_DONE_NOT_OK = "STATUS_DONE_NOT_OK"
        
        # Legacy aliases for backward compatibility
        ACCEPTED = "STATUS_ACK"
        IN_PROGRESS = "STATUS_EXECUTING"
        COMPLETED = "STATUS_DONE_OK"
        FAILED = "STATUS_DONE_NOT_OK"
        CANCELLED = "STATUS_DONE_NOT_OK"
        
    class ListenAsAgentRequest:
        def __init__(self, **kwargs): 
            for k, v in kwargs.items():
                setattr(self, k, v)
                
    class QueryTasksRequest:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        
    class UpdateStatusRequest:
        def __init__(self, status_update=None, **kwargs):
            # Debug logging for mock UpdateStatusRequest
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"=== MOCK UpdateStatusRequest DEBUG ===")
            logger.debug(f"status_update: {status_update}")
            logger.debug(f"kwargs: {kwargs}")
            
            self.status_update = status_update
            # Handle both nested dict structure and flat kwargs for compatibility
            if status_update and isinstance(status_update, dict):
                # Extract fields from nested structure
                version = status_update.get('version', {})
                self.task_id = version.get('task_id')
                self.status_version = version.get('status_version')
                status_info = status_update.get('status', {})
                self.status = status_info.get('status')
                self.progress_percentage = status_info.get('progress_percentage', 0.0)
                self.last_updated = status_update.get('last_updated')
                
                logger.debug(f"Parsed from nested structure:")
                logger.debug(f"  task_id: {self.task_id}")
                logger.debug(f"  status_version: {self.status_version}")
                logger.debug(f"  status: {self.status}")
                logger.debug(f"  progress_percentage: {self.progress_percentage}")
            else:
                # Fallback to flat structure
                for k, v in kwargs.items():
                    setattr(self, k, v)
                logger.debug(f"Set attributes from kwargs: {kwargs}")
    
    class TaskCatalog:
        """Mock TaskCatalog component for entities to be taskable"""
        def __init__(self, task_definitions=None):
            self.task_definitions = task_definitions or []
    
    class TaskDefinition:
        """Mock TaskDefinition with task specification URLs"""
        def __init__(self, task_type=None, specification_url=None, **kwargs):
            self.task_type = task_type or ""
            self.specification_url = specification_url or ""
            for k, v in kwargs.items():
                setattr(self, k, v)

# Mock Channel class for when grpclib is not available
class MockChannel:
    def __init__(self, host, port, ssl=True): 
        self.host = host
        self.port = port
        self.ssl = ssl
    async def __aenter__(self): 
        return self
    async def __aexit__(self, *args): 
        pass
    def close(self): 
        pass

class LatticeConnector:
    """
    REST v2 connector using the official Lattice Python SDK (`anduril`).
    - Publishes entities (assets) with telemetry
    - Listens for tasks via listen-as-agent
    - Updates task status
    """

    def __init__(self, config: Any) -> None:
        self.logger = logging.getLogger(__name__)

        self.logger.debug(f"Lattice SDK available: {LATTICE_SDK_AVAILABLE}")
        self.channel: Optional[Any] = None  # Use Any to avoid type conflicts
        self.client: Optional[Any] = None
        self.entity_manager_stub: Optional[EntityManagerApiStub] = None
        self.task_manager_stub: Optional[TaskManagerApiStub] = None
        self.is_connected = False
        
        # Global status version counter - follows sample app pattern exactly
        # Increments on every status update call, not per task
        self.status_version_counter: int = 1
        self._rest_verified_once: bool = False
        
        # Track completed tasks for cleanup to prevent memory leaks
        self.completed_tasks: set = set()

        # Log control knobs
        try:
            self.publish_info_interval_seconds = int(os.getenv("DRONE_PUBLISH_INFO_INTERVAL", "300"))
        except Exception:
            self.publish_info_interval_seconds = 300
        self._last_publish_info_log: dict[str, float] = {}
        self._last_invalid_location_warn: dict[str, float] = {}
        self._last_listen_warn: float = 0.0
        # Cache last known good location per drone to avoid UI flicker and allow partial-state publishes
        self._last_good_location: dict[str, dict[str, float]] = {}
        # Cache motion and orientation to always publish a complete frame
        self._last_good_velocity: dict[str, dict[str, float]] = {}
        self._last_good_heading: dict[str, float] = {}
        self._last_good_speed: dict[str, float] = {}
        
        # Authentication setup - standardized token handling with fallbacks
        self.bearer_token = (
            os.getenv('ENVIRONMENT_TOKEN')
            or os.getenv('LATTICE_BEARER_TOKEN')
            or os.getenv('LATTICE_TOKEN')
            or os.getenv('ANDURIL_BEARER_TOKEN')
            or getattr(config, 'bearer_token', None)
        )
        self.sandboxes_token = os.getenv('SANDBOXES_TOKEN') or getattr(config, 'sandboxes_token', None)
        # Resolve lattice URL: prefer env LATTICE_ENDPOINT, then LATTICE_URL, then config.url
        lattice_url_value = (
            os.getenv('LATTICE_ENDPOINT')
            or os.getenv('LATTICE_URL')
            or getattr(config, 'url', 'lattice.anduril.com')
        )
        # Expand ${ENV} placeholders if present
        if isinstance(lattice_url_value, str) and lattice_url_value.startswith('${') and lattice_url_value.endswith('}'):
            env_var_name = lattice_url_value[2:-1]
            lattice_url_value = os.getenv(env_var_name, lattice_url_value)
        self.lattice_url = lattice_url_value
        self.use_grpc = getattr(config, 'use_grpc', False)  # Default to REST per SDK v2
        
        # Setup metadata for authentication (grpclib expects list of (key, value))
        metadata_list = []
        if self.bearer_token:
            metadata_list.append((
                'authorization',
                f'Bearer {self.bearer_token}'
            ))
        if self.sandboxes_token:
            metadata_list.append((
                'anduril-sandbox-authorization',
                f'Bearer {self.sandboxes_token}'
            ))

        # Store as tuple list so every RPC shares the same object
        self.metadata = metadata_list

        # Determine integration/agent name used when watching tasks
        # Priority: explicit env var > middleware service name > default string
        self.integration_name = (
            os.getenv('LATTICE_AGENT_NAME')  # explicit override
            or os.getenv('SERVICE_NAME')      # propagated by container orchestrators
            or 'lattice-drone-middleware'
        )

        # Check what's available in the SDK (omit Activity component entirely)
        if REST_SDK_AVAILABLE and anduril is not None:
            self.logger.info("Checking available SDK components:")
            sdk_attrs = dir(anduril)
            has_task_status = "TaskStatus" in sdk_attrs
            has_task_catalog = "TaskCatalog" in sdk_attrs
            self.logger.info("SDK Component availability:")
            self.logger.info(f"  TaskStatus class: {'YES' if has_task_status else 'NO'}")
            self.logger.info(f"  TaskCatalog class: {'YES' if has_task_catalog else 'NO'}")
    
    async def connect(self):
        """Establish connection to Lattice platform"""
        try:
            # Validate authentication tokens
            is_sandbox_env = "sandboxes.developer.anduril.com" in self.lattice_url or \
                             ".env.sandboxes." in self.lattice_url
            if not self.bearer_token:
                self.logger.error("ENVIRONMENT_TOKEN (or LATTICE_BEARER_TOKEN/LATTICE_TOKEN) is not set")
                raise RuntimeError("Missing ENVIRONMENT_TOKEN for Lattice authentication")
            if is_sandbox_env and not self.sandboxes_token:
                self.logger.error("SANDBOXES_TOKEN is required for Sandboxes endpoints")
                raise RuntimeError("Missing SANDBOXES_TOKEN for Lattice Sandboxes authentication")

            # Initialize the high-level Lattice client (REST v2)
            if not REST_SDK_AVAILABLE or anduril is None:
                # Attempt to load local SDK path again if import was too early
                _ensure_local_anduril_on_path()
                try:
                    import anduril as _anduril  # type: ignore
                    globals()["anduril"] = _anduril
                    REST_SDK_AVAILABLE_LOCAL = True
                except Exception:
                    REST_SDK_AVAILABLE_LOCAL = False
            else:
                REST_SDK_AVAILABLE_LOCAL = True

            if REST_SDK_AVAILABLE_LOCAL and anduril is not None:
                try:
                    from anduril import Lattice  # type: ignore
                    
                    # Create headers for authentication
                    headers = {}
                    if self.sandboxes_token:
                        # Add sandbox authorization header (case-insensitive)
                        headers["Anduril-Sandbox-Authorization"] = f"Bearer {self.sandboxes_token}"
                    
                    # Initialize the Lattice client
                    self.client = Lattice(
                        base_url=f"https://{self.lattice_url}",
                        token=self.bearer_token,
                        headers=headers
                    )
                    self.logger.info("Initialized Lattice client for high-level API")
                except Exception as e:
                    self.logger.warning(f"Could not initialize Lattice client: {e}")
                    self.client = None
            else:
                self.client = None
            
            # Create secure gRPC channel for low-level API when requested
            if self.use_grpc and GRPC_AVAILABLE and GrpcChannel is not None:
                self.channel = GrpcChannel(
                    host=self.lattice_url,
                    port=443,
                    ssl=True  # grpclib uses SSL by default with True
                )
            else:
                # When not using gRPC, do not initialize any channel
                self.channel = None
            
            # Create stubs for entity and task management only if using gRPC
            if self.channel is not None:
                self.entity_manager_stub = EntityManagerApiStub(self.channel)
                self.task_manager_stub = TaskManagerApiStub(self.channel)
            else:
                self.entity_manager_stub = None
                self.task_manager_stub = None
            
            # Initialize mock state if using mock implementation
            if (
                not LATTICE_SDK_AVAILABLE
                and self.task_manager_stub is not None
                and hasattr(self.task_manager_stub, '_running')
            ):
                self.task_manager_stub._running = True
            
            self.is_connected = True
            if self.client is not None and self.use_grpc:
                self.logger.info(f"Connected to Lattice platform at {self.lattice_url} (REST client initialized, gRPC channel active)")
            elif self.client is not None:
                self.logger.info(f"Connected to Lattice platform at {self.lattice_url} (REST client initialized)")
            elif self.use_grpc:
                self.logger.info(f"Connected to Lattice platform at {self.lattice_url} (gRPC channel active)")
            else:
                self.logger.info(f"Connected to Lattice platform at {self.lattice_url} (mock channel for development)")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Lattice: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Lattice platform"""
        if self.channel and self.is_connected:
            # Stop the mock task watcher if running
            if self.task_manager_stub is not None and hasattr(self.task_manager_stub, '_running'):
                self.task_manager_stub._running = False
            
            self.channel.close()
            self.is_connected = False
            self.logger.info("Disconnected from Lattice platform")
    
    async def publish_entity(self, drone_id: str, telemetry_data: Dict[str, Any]) -> bool:
        """
        Publish drone as entity to Lattice platform
        
        Args:
            drone_id: Unique identifier for the drone
            telemetry_data: Current telemetry including position, battery, status
            
        Returns:
            True if published successfully, False otherwise
        """
        try:
            if not self.is_connected:
                self.logger.error("Not connected to Lattice platform")
                return False
            
            # Get current time for timestamps
            current_time = datetime.now(timezone.utc)
            
            # Extract position data with validation
            has_position = isinstance(telemetry_data, dict) and ("position" in telemetry_data)
            position_data = telemetry_data.get("position", {}) if has_position else {}
            lat = position_data.get("lat") if has_position else None
            lon = position_data.get("lon") if has_position else None
            # Use absolute altitude (HAE/AMSL) when available for correct UI altitude
            alt_rel = position_data.get("alt", 0.0) if has_position else 0.0
            alt_abs = position_data.get("absolute_alt", alt_rel) if has_position else 0.0

            # Update caches for motion/orientation regardless of position presence
            try:
                vel_td = telemetry_data.get("velocity") if isinstance(telemetry_data, dict) else None
                if isinstance(vel_td, dict):
                    self._last_good_velocity[drone_id] = {
                        "north": float(vel_td.get("north", 0.0)),
                        "east": float(vel_td.get("east", 0.0)),
                        "down": float(vel_td.get("down", 0.0)),
                    }
                if "heading" in telemetry_data and telemetry_data.get("heading") is not None:
                    self._last_good_heading[drone_id] = float(telemetry_data.get("heading", 0.0))
                if "speed_mps" in telemetry_data and telemetry_data.get("speed_mps") is not None:
                    self._last_good_speed[drone_id] = float(telemetry_data.get("speed_mps", 0.0))
            except Exception:
                pass

            # Optional GPS diagnostics if provided by connector
            gps_info = telemetry_data.get("gps", {}) if isinstance(telemetry_data, dict) else {}
            gps_fix = None
            try:
                gps_fix = gps_info.get("fix_type") if isinstance(gps_info, dict) else None
            except Exception:
                gps_fix = None

            # Validate location to avoid UI flicker
            valid_lat_lon = None
            try:
                if has_position:
                    valid_lat_lon = (
                        lat is not None and lon is not None and
                        abs(float(lat)) > 1e-6 and abs(float(lon)) > 1e-6
                    )
                else:
                    # Not a location update; do not treat as invalid
                    valid_lat_lon = None
            except Exception:
                valid_lat_lon = False

            # Determine location object and uncertainty based on validity
            # Always publish to keep expiry moving; if invalid, prefer last-known position with large uncertainty
            location_obj_rest = None
            location_uncertainty_rest = None
            if valid_lat_lon is True:
                # Update cache and build normal location
                lat_safe = float(cast(float, lat))
                lon_safe = float(cast(float, lon))
                alt_safe = float(alt_abs)
                self._last_good_location[drone_id] = {
                    "lat": lat_safe,
                    "lon": lon_safe,
                    "alt_abs": alt_safe,
                }
            elif valid_lat_lon is False:
                now_monotonic = asyncio.get_event_loop().time()
                last_warn = self._last_invalid_location_warn.get(drone_id, 0.0)
                if now_monotonic - last_warn >= 10.0:
                    self.logger.warning(
                        "Invalid location for %s lat=%s lon=%s gps_fix=%s; publishing with uncertainty",
                        drone_id, lat, lon, gps_fix
                    )
                    self._last_invalid_location_warn[drone_id] = now_monotonic
            else:
                # No position provided; keep previous position without warnings
                pass
            
            self.logger.debug(f"Creating entity for drone {drone_id} at position ({lat}, {lon}, {alt_abs})")
            
            # REST path (preferred)
            if self.client is not None and REST_SDK_AVAILABLE and anduril is not None:
                try:
                    now = current_time
                    client = self.client
                    assert client is not None
                    # Always include sandbox header per request as well
                    request_options = None
                    try:
                        request_options = {  # type: ignore[assignment]
                            # Long-poll safe timeout for listen/publish scenarios
                            "timeout_in_seconds": 330,
                        }
                        if self.sandboxes_token:
                            request_options["additional_headers"] = {  # type: ignore[index]
                                "Anduril-Sandbox-Authorization": f"Bearer {self.sandboxes_token}",
                            }
                    except Exception:
                        request_options = None
                    if request_options:
                        self.logger.debug("REST publish request_options.additional_headers set (sandbox header present)")
                    # Compute motion fields with cached fallbacks
                    vel = telemetry_data.get("velocity") or {}
                    if not vel:
                        vel = self._last_good_velocity.get(drone_id, {"north": 0.0, "east": 0.0, "down": 0.0})
                    v_e = float(vel.get("east", 0.0))
                    v_n = float(vel.get("north", 0.0))
                    v_u = -float(vel.get("down", 0.0))  # NED down -> ENU up
                    speed_mps_calc = (v_e ** 2 + v_n ** 2 + v_u ** 2) ** 0.5
                    # Prefer explicit speed, else cached, else derived
                    if telemetry_data.get("speed_mps") is not None:
                        speed_mps = float(telemetry_data.get("speed_mps", speed_mps_calc))
                    else:
                        _cached_speed = self._last_good_speed.get(drone_id)
                        speed_mps = float(_cached_speed) if _cached_speed is not None else float(speed_mps_calc)

                    # Optional attitude quaternion from heading (omitted to satisfy static typing)
                    attitude_obj = None

                    # Build location with velocity and speed always present (even zeros)
                    cached_loc = self._last_good_location.get(drone_id)
                    if valid_lat_lon is True:
                        # Narrow types for the type checker
                        lat_f = float(cast(float, lat))
                        lon_f = float(cast(float, lon))
                        alt_f = float(alt_abs)
                        LocationClass = getattr(anduril, "Location", None)
                        PositionClass = getattr(anduril, "Position", None)
                        EnuClass = getattr(anduril, "Enu", None)
                        if LocationClass is not None and PositionClass is not None:
                            if EnuClass is not None:
                                velocity_enu_obj = EnuClass(e=float(v_e), n=float(v_n), u=float(v_u))  # type: ignore[call-arg]
                            else:
                                velocity_enu_obj = None
                            location_obj_rest = LocationClass(  # type: ignore[call-arg]
                                position=PositionClass(  # type: ignore[call-arg]
                                    latitude_degrees=lat_f,
                                    longitude_degrees=lon_f,
                                    altitude_hae_meters=alt_f,
                                ),
                                velocity_enu=velocity_enu_obj,
                                speed_mps=float(speed_mps),
                                attitude_enu=attitude_obj,
                            )
                    elif valid_lat_lon is False and cached_loc is not None:
                        cached = cached_loc
                        LocationClass = getattr(anduril, "Location", None)
                        PositionClass = getattr(anduril, "Position", None)
                        EnuClass = getattr(anduril, "Enu", None)
                        if LocationClass is not None and PositionClass is not None:
                            if EnuClass is not None:
                                velocity_enu_obj = EnuClass(e=float(v_e), n=float(v_n), u=float(v_u))  # type: ignore[call-arg]
                            else:
                                velocity_enu_obj = None
                            location_obj_rest = LocationClass(  # type: ignore[call-arg]
                                position=PositionClass(  # type: ignore[call-arg]
                                    latitude_degrees=float(cached["lat"]),
                                    longitude_degrees=float(cached["lon"]),
                                    altitude_hae_meters=float(cached["alt_abs"]),
                                ),
                                velocity_enu=velocity_enu_obj,  # include motion to keep heading/speed visible
                                speed_mps=float(speed_mps),
                                attitude_enu=attitude_obj,
                            )
                        # Provide uncertainty when we don't trust the current fix
                        try:
                            location_uncertainty_rest = anduril.LocationUncertainty(  # type: ignore[attr-defined]
                                position_error_ellipse=anduril.ErrorEllipse(  # type: ignore[attr-defined]
                                    probability=0.5,
                                    semi_major_axis_m=1000.0,
                                    semi_minor_axis_m=1000.0,
                                    orientation_d=0.0,
                                )
                            )
                        except Exception:
                            location_uncertainty_rest = None
                    elif cached_loc is not None:
                        # No new position; reuse cached to avoid UI reset
                        LocationClass = getattr(anduril, "Location", None)
                        PositionClass = getattr(anduril, "Position", None)
                        EnuClass = getattr(anduril, "Enu", None)
                        if LocationClass is not None and PositionClass is not None:
                            if EnuClass is not None:
                                velocity_enu_obj = EnuClass(e=float(v_e), n=float(v_n), u=float(v_u))  # type: ignore[call-arg]
                            else:
                                velocity_enu_obj = None
                            location_obj_rest = LocationClass(  # type: ignore[call-arg]
                                position=PositionClass(  # type: ignore[call-arg]
                                    latitude_degrees=float(cached_loc["lat"]),
                                    longitude_degrees=float(cached_loc["lon"]),
                                    altitude_hae_meters=float(cached_loc["alt_abs"]),
                                ),
                                velocity_enu=velocity_enu_obj,
                                speed_mps=float(speed_mps),
                                attitude_enu=attitude_obj,
                            )
                    else:
                        # No cached location yet; skip publish to avoid clearing UI
                        self.logger.warning(f"No location available yet for {drone_id}; deferring publish to avoid UI reset")
                        return False

                    # Build ontology object and add specific_type if supported by SDK
                    try:
                        _OntologyClass = getattr(anduril, "Ontology", None)
                        ontology_obj_rest = None
                        if _OntologyClass is not None:
                            try:
                                ontology_obj_rest = _OntologyClass(  # type: ignore[call-arg]
                                    template="TEMPLATE_ASSET",
                                    platform_type="UAV",
                                )
                                # Try to set specific_type attribute if supported
                                try:
                                    setattr(ontology_obj_rest, "specific_type", "Drone")
                                except Exception:
                                    pass
                            except Exception:
                                ontology_obj_rest = _OntologyClass(  # type: ignore[call-arg]
                                    template="TEMPLATE_ASSET",
                                    platform_type="UAV",
                                )
                        else:
                            ontology_obj_rest = getattr(anduril, "Ontology")(template="TEMPLATE_ASSET", platform_type="UAV")  # type: ignore[call-arg]
                    except Exception:
                        ontology_obj_rest = getattr(anduril, "Ontology")(template="TEMPLATE_ASSET", platform_type="UAV")  # type: ignore[call-arg]

                    # Build publish kwargs; location is always included here
                    publish_kwargs = {
                        "entity_id": drone_id,
                        "description": "Drone asset managed by lattice-drone-control",
                        "is_live": True,
                        "created_time": now,
                        "expiry_time": now + timedelta(minutes=10),
                        "aliases": getattr(anduril, "Aliases")(name=f"Drone-{drone_id}"),  # type: ignore[call-arg]
                        "ontology": ontology_obj_rest,
                        "provenance": getattr(anduril, "Provenance")(  # type: ignore[call-arg]
                            integration_name="lattice-drone-control",
                            data_type="drone_telemetry",
                            source_update_time=now,
                            source_description="Lattice Drone Control System",
                        ),
                        "health": getattr(anduril, "Health")(  # type: ignore[call-arg]
                            connection_status="CONNECTION_STATUS_ONLINE",
                            health_status="HEALTH_STATUS_HEALTHY",
                            update_time=now,
                        ),
                        "mil_view": getattr(anduril, "MilView")(disposition="DISPOSITION_FRIENDLY", environment="ENVIRONMENT_AIR"),  # type: ignore[call-arg]
                        "location": location_obj_rest,
                        "task_catalog": (
                            getattr(anduril, "TaskCatalog")(  # type: ignore[call-arg]
                                task_definitions=[
                                    getattr(anduril, "TaskDefinition")(task_specification_url=url)  # type: ignore[call-arg]
                                    for url in [
                                        "type.googleapis.com/anduril.tasks.v2.VisualId",
                                        "type.googleapis.com/anduril.tasks.v2.Investigate",
                                        "type.googleapis.com/anduril.tasks.v2.Monitor",
                                    ]
                                ]
                            )
                        ),
                    }
                    if location_uncertainty_rest is not None:
                        publish_kwargs["location_uncertainty"] = location_uncertainty_rest

                    # Activity component intentionally omitted: Activity class not available in SDK

                    await asyncio.to_thread(
                        client.entities.publish_entity,
                        request_options=request_options,
                        **publish_kwargs,
                    )
                    # Reduce repetitive INFO logs; only elevate to INFO periodically
                    self._log_publish_success(drone_id, via="REST")
                    # One-time verification: fetch the entity back and log key fields
                    if not self._rest_verified_once:
                        try:
                            # Include headers on get as well
                            returned = await asyncio.to_thread(
                                client.entities.get_entity,
                                entity_id=drone_id,
                            )
                            returned_id = getattr(returned, "entity_id", None)
                            returned_aliases = getattr(returned, "aliases", None)
                            returned_name = getattr(returned_aliases, "name", None) if returned_aliases else None
                            returned_ontology = getattr(returned, "ontology", None)
                            returned_platform_type = getattr(returned_ontology, "platform_type", None) if returned_ontology else None
                            self.logger.info(
                                f"Verified entity via REST: entity_id={returned_id}, aliases.name={returned_name}, ontology.platform_type={returned_platform_type}"
                            )
                            self._rest_verified_once = True
                        except Exception as verify_exc:
                            self.logger.warning(f"REST verification get_entity failed: {verify_exc}")
                    return True
                except Exception as rest_exc:
                    if not self.use_grpc:
                        self.logger.error(f"REST publish failed and gRPC is disabled: {rest_exc}")
                        return False
                    self.logger.warning(f"REST publish failed, attempting gRPC fallback: {rest_exc}")

            # gRPC fallback path
            # Create position from telemetry (gRPC types) with safe casting
            try:
                lat_f = float(lat) if lat is not None else 0.0
                lon_f = float(lon) if lon is not None else 0.0
                alt_f = float(alt_abs)
            except Exception:
                lat_f, lon_f, alt_f = 0.0, 0.0, float(alt_abs) if isinstance(alt_abs, (int, float)) else 0.0
            position = Position(
                latitude_degrees=lat_f,  # type: ignore[arg-type]
                longitude_degrees=lon_f,  # type: ignore[arg-type]
                altitude_hae_meters=alt_f  # type: ignore[arg-type]
            )
            
            
            # Create TaskCatalog component so the asset becomes task-able in Lattice UI (gRPC)
            # Build TaskCatalog so UI knows what tasks the UAV accepts
            # Build TaskCatalog so UI knows what tasks the UAV accepts
            try:
                import inspect, dataclasses
                spec_urls = [
                    # Use the correct type.googleapis.com format as shown in Lattice SDK docs
                    "type.googleapis.com/anduril.tasks.v2.Monitor",
                    "type.googleapis.com/anduril.tasks.v2.Investigate",
                    "type.googleapis.com/anduril.tasks.v2.VisualId",
                ]
                td_params = inspect.signature(TaskDefinition).parameters
                task_defs = []
                for url in spec_urls:
                    # Based on sample app, use task_specification_url
                    task_defs.append(TaskDefinition(task_specification_url=url))
                task_catalog = TaskCatalog(task_definitions=task_defs)
                self.logger.debug("Added TaskCatalog with %d definitions", len(task_catalog.task_definitions))
            except Exception as catalog_err:
                task_catalog = None  # ensure defined
                # We can still publish the entity without a catalog; just log the issue
                self.logger.warning(f"Failed to build TaskCatalog: {catalog_err}")
            
            # Create entity with all required components per Lattice SDK documentation (gRPC)
            entity_kwargs = {
                "entity_id": drone_id,
                "description": "Drone asset managed by lattice-drone-control",
                "is_live": True,  # Required field
                "created_time": current_time,
                "expiry_time": current_time + timedelta(minutes=10),
                
                # Required aliases component
                "aliases": Aliases(name=f"Drone-{drone_id}"),
                
                # Required location component
                "location": Location(position=position),
                
                # Required ontology component for asset template
                "ontology": Ontology(
                    template=Template.ASSET,
                    platform_type="UAV",
                ),
                
                # Required provenance component
                "provenance": Provenance(
                    integration_name="lattice-drone-control",
                    data_type="drone_telemetry",
                    source_update_time=current_time,
                    source_description="Lattice Drone Control System"
                ),
                
                # Military view component for asset classification
                "mil_view": MilView(
                    disposition=Disposition.FRIENDLY,
                    environment=Environment.AIR
                ),

                # Health component so the asset is ONLINE and taskable when using gRPC
                "health": {
                    "connection_status": "CONNECTION_STATUS_ONLINE",
                    "health_status": "HEALTH_STATUS_HEALTHY",
                    "update_time": current_time,
                }
            }
            # Try to set specific_type on ontology if supported by the SDK
            try:
                ont_obj = entity_kwargs.get("ontology")
                if ont_obj is not None:
                    setattr(ont_obj, "specific_type", "Drone")
            except Exception:
                pass

            
            # Activity component intentionally omitted for gRPC path

            # Add TaskCatalog only if using real SDK (avoids serialization issues in mock mode)
            if task_catalog is not None:
                entity_kwargs["task_catalog"] = task_catalog
            
            entity = Entity(**entity_kwargs)
            
            # Log entity summary for troubleshooting
            self.logger.debug(f"Entity kwargs: {entity_kwargs}")
            if task_catalog is None:
                self.logger.error("TaskCatalog missing – asset will not be taskable in UI")
            else:
                self.logger.info(f"TaskCatalog created with {len(task_catalog.task_definitions)} task definitions")
                # Log the actual task definitions being sent
                for i, td in enumerate(task_catalog.task_definitions):
                    self.logger.info(f"  TaskDefinition[{i}]: url={td.task_specification_url}")
                # Check if entity has task_catalog after construction
                if hasattr(entity, 'task_catalog'):
                    self.logger.info(f"Entity has task_catalog attribute: {getattr(entity, 'task_catalog', None) is not None}")
                else:
                    self.logger.error("Entity does NOT have task_catalog attribute!")

            # Publish to Lattice with authentication metadata (gRPC)
            if self.entity_manager_stub:
                try:
                    request = PublishEntityRequest(entity=entity)
                    self.logger.info(f"Publishing entity {drone_id} to Lattice with position: lat={position.latitude_degrees}, lon={position.longitude_degrees}, alt={position.altitude_hae_meters}")
                    
                    response = await self.entity_manager_stub.publish_entity(
                        request,
                        metadata=self.metadata
                    )
                    self.logger.debug(f"publish_entity response: {response}")

                    # Immediately fetch back the entity to verify TaskCatalog was stored
                    try:
                        if hasattr(self.entity_manager_stub, "get_entity"):
                            get_entity_fn = getattr(self.entity_manager_stub, "get_entity")  # type: ignore[attr-defined]
                            verify_resp = await get_entity_fn(
                                GetEntityRequest(entity_id=drone_id),
                                metadata=self.metadata,
                            )
                            tc = getattr(verify_resp.entity, "task_catalog", None)
                            self.logger.debug("Server task_catalog for %s: %s", drone_id, tc)
                            if tc is None or not getattr(tc, "task_definitions", []):
                                self.logger.error("Server is missing TaskCatalog – asset will remain untaskable")
                    except Exception as verify_err:
                        self.logger.warning("Could not verify TaskCatalog via get_entity: %s", verify_err)
                    
                    # Check response - in actual SDK, check specific response fields
                    if not getattr(response, 'success', True):
                        self.logger.error(f"Lattice rejected entity publication for drone {drone_id}")
                        return False
                    
                    # Reduce repetitive INFO logs; only elevate to INFO periodically
                    self._log_publish_success(drone_id, via="gRPC")
                    return True
                    
                except Exception as publish_error:
                    self.logger.error(f"Failed to publish entity request for drone {drone_id}: {publish_error}")
                    # Still return False but don't re-raise to allow retries
                    return False
            else:
                self.logger.error("Entity manager stub not properly initialized (no gRPC channel)")
                return False
                
        except Exception as e:
            self.logger.error(f"Error publishing entity for drone {drone_id}: {e}")
            return False
    
    async def watch_tasks(self, callback, drone_ids: Optional[list] = None):
        """
        Watch for tasks assigned to our drones using listen_as_agent
        
        Args:
            callback: Function to call when new task is received
            drone_ids: List of drone IDs to watch tasks for (optional)
        """
        try:
            if not self.is_connected:
                self.logger.error("Not connected to Lattice platform")
                return
            
            # Determine which API to use for task watching
            use_rest = self.client is not None and REST_SDK_AVAILABLE and anduril is not None
            use_grpc = self.use_grpc and self.task_manager_stub is not None
            
            # REST path - prioritize when available and not explicitly using gRPC
            if use_rest and not self.use_grpc:
                assignee_ids = drone_ids or [self.integration_name]
                selector = anduril.EntityIdsSelector(entity_ids=assignee_ids)  # type: ignore[attr-defined]
                
                try:
                    client = self.client
                    assert client is not None
                    
                    # Include sandbox header per request
                    request_options = {
                        "timeout_in_seconds": 330,  # Long-poll timeout
                    }
                    if self.sandboxes_token:
                        request_options["additional_headers"] = { # type: ignore
                            "Anduril-Sandbox-Authorization": f"Bearer {self.sandboxes_token}",
                        }
                    
                    self.logger.info(f"Starting REST listen_as_agent for assignees: {assignee_ids}")
                    
                    # Continuous polling loop for REST
                    while True:
                        try:
                            # Make the listen_as_agent call with long polling
                            agent_request = await asyncio.to_thread(
                                client.tasks.listen_as_agent,
                                agent_selector=selector,
                                request_options=request_options,
                            )
                            
                            # Process the received request
                            req_type = "unknown"
                            task_id = None
                            
                            # Identify request type
                            if getattr(agent_request, "execute_request", None) is not None:
                                req_type = "execute"
                                tx = agent_request.execute_request
                                try:
                                    version = getattr(getattr(tx, "task", None), "version", None)
                                    task_id = getattr(version, "task_id", None)
                                except Exception:
                                    task_id = None
                            elif getattr(agent_request, "cancel_request", None) is not None:
                                req_type = "cancel"
                                try:
                                    task_id = getattr(agent_request.cancel_request, "task_id", None) or \
                                             getattr(agent_request.cancel_request, "taskId", None)
                                except Exception:
                                    task_id = None
                            elif getattr(agent_request, "complete_request", None) is not None:
                                req_type = "complete"
                                try:
                                    task_id = getattr(agent_request.complete_request, "task_id", None) or \
                                             getattr(agent_request.complete_request, "taskId", None)
                                except Exception:
                                    task_id = None
                            
                            self.logger.info(f"REST AgentRequest received type={req_type} task_id={task_id}")
                            
                            # Forward valid requests to callback
                            should_forward = False
                            if req_type == "execute" and task_id:
                                should_forward = True
                            elif req_type in ["cancel", "complete"]:
                                should_forward = True  # Forward even without task_id, let handler validate
                            
                            if should_forward:
                                await callback(agent_request)
                            else:
                                self.logger.debug("Ignoring agent request (likely keep-alive)")
                                
                        except asyncio.TimeoutError:
                            # Expected timeout from long polling - just continue
                            self.logger.debug("REST listen_as_agent poll timeout (expected)")
                            await asyncio.sleep(0.1)  # Brief pause before retrying
                        except Exception as poll_error:
                            # Log polling errors with rate limiting
                            now_mono = asyncio.get_event_loop().time()
                            if now_mono - self._last_listen_warn >= 60.0:
                                self.logger.debug(f"REST listen_as_agent error: {poll_error}")
                                self._last_listen_warn = now_mono
                            await asyncio.sleep(1)  # Backoff on error
                            
                except Exception as exc:
                    self.logger.error(f"REST listen_as_agent setup failed: {exc}")
                    raise  # Re-raise to trigger retry in TaskManager
                
            # gRPC path - only if explicitly requested and available
            elif use_grpc:
                self.logger.info("Starting task watcher using gRPC")
                
                # Build request with entity_ids
                entity_ids_list = drone_ids or [self.integration_name]
                request_data = {
                    'entity_ids': {
                        'entity_ids': entity_ids_list
                    }
                }
                
                self.logger.debug(f"Creating ListenAsAgentRequest with data: {request_data}")
                
                try:
                    request = ListenAsAgentRequest.from_dict(request_data)  # type: ignore
                except:
                    request = ListenAsAgentRequest()
                    if hasattr(request, 'entity_ids'):
                        request.entity_ids = request_data['entity_ids']  # type: ignore
                
                # Listen for tasks using gRPC streaming
                task_stream = self.task_manager_stub.listen_as_agent( # type: ignore
                    request, 
                    metadata=self.metadata
                )
                
                # Process gRPC stream
                async for task in task_stream:  # type: ignore
                    try:
                        response_type = "unknown"
                        if hasattr(task, 'execute_request'):
                            response_type = "execute_request"
                        elif hasattr(task, 'cancel_request'):
                            response_type = "cancel_request"
                        elif hasattr(task, 'complete_request'):
                            response_type = "complete_request"
                        
                        self.logger.info(f"Received ListenAsAgentResponse from Lattice: type={response_type}")
                        await callback(task)
                    except Exception as e:
                        self.logger.error(f"Error processing task: {e}")
                        
            else:
                # Neither REST nor gRPC available
                error_msg = []
                if not use_rest:
                    error_msg.append("REST client not available")
                if not use_grpc and self.use_grpc:
                    error_msg.append("gRPC stub not initialized but gRPC requested")
                
                self.logger.error(f"Cannot watch tasks: {', '.join(error_msg)}")
                raise RuntimeError(f"Task watching not available: {', '.join(error_msg)}")
                
        except asyncio.CancelledError:
            self.logger.info("Task watcher cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Task watcher error: {e}")
            raise  # Re-raise so TaskManager can handle retry logic
    
    async def update_task_status(self, task_id: str, status: str, progress: float = 0.0, author_entity_id: Optional[str] = None) -> bool:
        """
        Update task execution status in Lattice using update_task_status
        
        Args:
            task_id: Task identifier
            status: Current status (STATUS_ACK, STATUS_WILCO, STATUS_EXECUTING, etc.)
            progress: Completion percentage (0.0 to 1.0)
            author_entity_id: Optional entity ID of the agent updating the status
            
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            self.logger.info(f"Updating task status: task_id={task_id}, status={status}, progress={progress}, author={author_entity_id}")
            
            if not self.is_connected:
                self.logger.error("Not connected to Lattice platform")
                return False
            
            # Increment global status version counter
            self.status_version_counter += 1
            current_version = self.status_version_counter
            self.logger.debug(f"Using status version: {current_version}")
            
            # Clean up completed tasks to prevent memory leaks
            status_constants = self.get_status_constants()
            if status in [status_constants.STATUS_DONE_OK, status_constants.STATUS_DONE_NOT_OK]:
                self.completed_tasks.add(task_id)
                asyncio.create_task(self._cleanup_completed_task(task_id))
            
            # REST SDK path - prioritize when available
            if REST_SDK_AVAILABLE and self.client is not None and anduril is not None:
                try:
                    # Create TaskStatus object
                    TaskStatusClass = getattr(anduril, "TaskStatus", None)
                    if TaskStatusClass is None:
                        self.logger.error("TaskStatus class not found in REST SDK")
                        return False
                    
                    # Create new status with the status string
                    new_status = TaskStatusClass(status=status)
                    
                    # Create author Principal if entity_id provided
                    author = None
                    if author_entity_id:
                        try:
                            PrincipalClass = getattr(anduril, "Principal", None)
                            SystemClass = getattr(anduril, "System", None)
                            if PrincipalClass and SystemClass:
                                author = PrincipalClass(
                                    system=SystemClass(
                                        entity_id=author_entity_id,
                                        service_name="lattice-drone-control"
                                    )
                                )
                        except Exception as e:
                            self.logger.debug(f"Could not create author Principal: {e}")
                    
                    # Build update arguments
                    update_args = {
                        "task_id": task_id,
                        "new_status": new_status,
                        "status_version": current_version,
                    }
                    if author is not None:
                        update_args["author"] = author
                    
                    # Include sandbox header if needed
                    request_options = {}
                    if self.sandboxes_token:
                        request_options["additional_headers"] = {
                            "Anduril-Sandbox-Authorization": f"Bearer {self.sandboxes_token}",
                        }
                    
                    # Call the REST API
                    self.logger.debug(f"Calling REST update_task_status with args: task_id={task_id}, status={status}, version={current_version}")
                    
                    if request_options:
                        response = await asyncio.to_thread(
                            self.client.tasks.update_task_status,
                            **update_args,
                            request_options=request_options
                        )
                    else:
                        response = await asyncio.to_thread(
                            self.client.tasks.update_task_status,
                            **update_args
                        )
                    
                    self.logger.info(f"Successfully updated task {task_id} status to {status} (version {current_version})")
                    return True
                    
                except Exception as e:
                    self.logger.error(f"REST update_task_status failed: {e}")
                    
                    # If REST fails and gRPC is enabled, try gRPC as fallback
                    if self.use_grpc and self.task_manager_stub:
                        self.logger.info("Attempting gRPC fallback for update_task_status")
                        # Fall through to gRPC code below
                    else:
                        return False
            
            # gRPC fallback path (only if REST unavailable or failed and gRPC is enabled)
            if self.use_grpc and self.task_manager_stub and LATTICE_SDK_AVAILABLE:
                try:
                    from anduril.taskmanager.v1 import UpdateStatusRequest, TaskStatus
                    
                    # Create status object
                    new_status = TaskStatus()
                    if hasattr(new_status, 'status'):
                        new_status.status = status # type: ignore
                    
                    # Create request
                    request = UpdateStatusRequest()
                    if hasattr(request, 'status_update'):
                        request.status_update = new_status # type: ignore
                    elif hasattr(request, 'new_status'):
                        request.new_status = new_status
                    
                    if hasattr(request, 'task_id'):
                        request.task_id = task_id
                    if hasattr(request, 'status_version'):
                        request.status_version = str(current_version)
                    
                    # Add author if provided
                    if author_entity_id and hasattr(request, 'author'):
                        try:
                            from anduril import Principal, System # type: ignore
                            request.author = Principal(
                                system=System(entity_id=author_entity_id)
                            )
                        except ImportError:
                            pass
                    
                    # Call gRPC update
                    response = await self.task_manager_stub.update_status(
                        request,
                        metadata=self.metadata
                    )
                    
                    self.logger.info(f"Successfully updated task {task_id} status to {status} via gRPC")
                    return True
                    
                except Exception as e:
                    self.logger.error(f"gRPC update_task_status failed: {e}")
                    return False
            
            # If we get here, neither REST nor gRPC worked
            self.logger.error(f"No available method to update task status for {task_id}")
            return False
            
        except Exception as e:
            self.logger.error(f"Error updating task status for task {task_id}: {e}")
            return False
            
    async def _cleanup_completed_task(self, task_id: str, delay: int = 300):
        """
        Clean up task status versions after a delay to prevent memory leaks
        
        Args:
            task_id: Task identifier to clean up
            delay: Delay in seconds before cleanup (default 5 minutes)
        """
        try:
            await asyncio.sleep(delay)
            
            # Only clean up if task is marked as completed
            if task_id in self.completed_tasks:
                self.completed_tasks.discard(task_id)
                self.logger.debug(f"Cleaned up completed task {task_id}")
                
        except Exception as e:
            self.logger.error(f"Error during task cleanup for {task_id}: {e}")
            
    async def query_tasks(self, filters: Optional[Dict[str, Any]] = None) -> list:
        """
        Query for tasks from Lattice platform
        
        Args:
            filters: Optional filters for task query
            
        Returns:
            List of tasks matching the query
        """
        try:
            if not self.is_connected:
                self.logger.error("Not connected to Lattice platform") 
                return []
            
            if not self.task_manager_stub:
                self.logger.error("Task manager stub not initialized")
                return []
            
            # Create query request
            request = QueryTasksRequest()
            if filters:
                # Add filters to request based on SDK documentation
                for key, value in filters.items():
                    setattr(request, key, value)
            
            response = await self.task_manager_stub.query_tasks(
                request,
                metadata=self.metadata
            )
            
            # Return tasks from response
            return getattr(response, 'tasks', [])
            
        except Exception as e:
            self.logger.error(f"Error querying tasks: {e}")
            return []
    
    def get_status_constants(self):
        """
        Get the appropriate task status constants based on SDK availability
        
        Returns:
            TaskStatus constants class (either real SDK or mock)
        """
        if LATTICE_SDK_AVAILABLE:
            return TASK_STATUS
        else:
            return TaskStatus 

    def _log_publish_success(self, drone_id: str, via: str) -> None:
        """Rate-limit noisy publish success INFO logs.
        Always emit DEBUG; emit INFO only every N seconds per drone.
        """
        try:
            now_mono = asyncio.get_event_loop().time()
        except Exception:
            # Fallback if event loop not available
            import time as _time
            now_mono = _time.monotonic()

        last = self._last_publish_info_log.get(drone_id, 0.0)
        if now_mono - last >= max(5, self.publish_info_interval_seconds):
            self._last_publish_info_log[drone_id] = now_mono
            self.logger.info("Successfully published entity for drone %s via %s", drone_id, via)
        else:
            self.logger.debug("Published entity for drone %s via %s", drone_id, via)