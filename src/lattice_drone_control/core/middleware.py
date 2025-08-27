"""
Core middleware orchestrator that coordinates between Lattice and drone flight controllers
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

from ..connectors.lattice import LatticeConnector
from ..connectors.mavsdk import MAVSDKConnector
from .entity_manager import EntityManager
from .task_manager import TaskManager
from .state_manager import StateManager
from ..models.config import MiddlewareConfig
from ..models.drone import DroneState
from ..utils.metrics import MetricsCollector

class DroneMiddleware:
    """
    Main middleware class that orchestrates communication between Lattice platform
    and drone flight controllers, enabling autonomous task switching
    """
    
    def __init__(self, config: MiddlewareConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        
        # Check if we're running in mock mode (no Lattice)
        self.mock_mode = getattr(config, 'mock_mode', False) or not hasattr(config, 'lattice')
        
        # Core components
        if self.mock_mode:
            self.logger.warning("Running in MOCK MODE - Lattice connection disabled")
            self.lattice_connector = None
            self.entity_manager = None
            self.task_manager = None
        else:
            self.lattice_connector = LatticeConnector(config.lattice)
            self.entity_manager = EntityManager(self.lattice_connector)
            self.task_manager = TaskManager(self.lattice_connector, self)
            
        self.state_manager = StateManager()
        self.metrics = MetricsCollector()
        
        # Drone connections - maps drone_id to MAVSDKConnector
        self.drone_connectors: Dict[str, MAVSDKConnector] = {}
        
        # Task execution tracking
        self.active_tasks: Dict[str, str] = {}  # drone_id -> task_id
        
    async def start(self):
        """Start the middleware service"""
        try:
            self.logger.info("Starting Lattice drone middleware...")
            
            # Initialize Lattice connection if not in mock mode
            if not self.mock_mode and self.lattice_connector:
                await self.lattice_connector.connect()
                self.logger.info("Connected to Lattice platform")
            else:
                self.logger.info("Running in mock mode - skipping Lattice connection")
            
            # Connect to configured drones
            await self._connect_drones()
            
            # Start core services (only if not in mock mode)
            if not self.mock_mode:
                if self.entity_manager:
                    asyncio.create_task(self.entity_manager.start_telemetry_publisher())
                if self.task_manager:
                    asyncio.create_task(self.task_manager.start_task_watcher())
            
            # Always start health monitor
            asyncio.create_task(self._health_monitor())
            
            self.is_running = True
            self.logger.info(f"Middleware started with {len(self.drone_connectors)} drones")
            
        except Exception as e:
            self.logger.error(f"Failed to start middleware: {e}")
            raise
    
    async def shutdown(self):
        """Gracefully shutdown the middleware"""
        self.logger.info("Shutting down middleware...")
        self.is_running = False
        
        # Stop all active tasks
        for drone_id in list(self.active_tasks.keys()):
            await self.stop_task(drone_id)
        
        # Disconnect from drones
        for connector in self.drone_connectors.values():
            await connector.disconnect()
        
        # Disconnect from Lattice (if not in mock mode)
        if not self.mock_mode and self.lattice_connector:
            await self.lattice_connector.disconnect()
        
        self.logger.info("Middleware shutdown complete")
    
    async def _connect_drones(self):
        """Connect to all configured drones"""
        for drone_config in self.config.drones:
            try:
                connector = MAVSDKConnector(drone_config)
                await connector.connect()
                
                # Initialize drone state
                drone_state = DroneState(
                    drone_id=drone_config.id,
                    connection_string=drone_config.connection_string,
                    status="CONNECTED",
                    last_update=datetime.now(timezone.utc)
                )
                
                self.drone_connectors[drone_config.id] = connector
                self.state_manager.update_drone_state(drone_config.id, drone_state)

                # Attach connector reference for live telemetry in EntityManager
                setattr(drone_state, "_connector", connector)
                
                # Register as entity in Lattice (if not in mock mode)
                if not self.mock_mode and self.entity_manager:
                    await self.entity_manager.register_drone(drone_config.id, drone_state)
                
                self.logger.info(f"Connected to drone {drone_config.id}")
                
            except Exception as e:
                self.logger.error(f"Failed to connect to drone {drone_config.id}: {e}")
    
    async def execute_task(self, drone_id: str, task_type: str, task_params: dict) -> bool:
        """
        Execute a task on the specified drone with on-the-fly switching capability
        
        Args:
            drone_id: Target drone identifier
            task_type: Type of task (mapping, relay, dropping)
            task_params: Task-specific parameters
            
        Returns:
            True if task started successfully, False otherwise
        """
        try:
            # Check if drone is available
            if drone_id not in self.drone_connectors:
                self.logger.error(f"Drone {drone_id} not connected")
                return False
            
            connector = self.drone_connectors[drone_id]
            
            # Stop current task if running
            if drone_id in self.active_tasks:
                await self.stop_task(drone_id)
            
            # Import and execute the appropriate task
            if task_type == "mapping":
                from ..tasks.mapping import MappingTask
                task = MappingTask(connector, task_params)
            elif task_type == "relay":
                from ..tasks.relay import RelayTask
                task = RelayTask(connector, task_params)
            elif task_type == "dropping":
                from ..tasks.dropping import DroppingTask
                task = DroppingTask(connector, task_params)
            else:
                self.logger.error(f"Unknown task type: {task_type}")
                return False
            
            # Start and run task to completion so callers can reflect true outcome
            task_id = f"{drone_id}_{task_type}_{datetime.now().isoformat()}"
            self.active_tasks[drone_id] = task_id
            
            self.logger.info(f"Started {task_type} task on drone {drone_id}")
            result = await self._run_task(drone_id, task_id, task)
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to execute task on drone {drone_id}: {e}")
            return False
    
    async def _run_task(self, drone_id: str, task_id: str, task) -> bool:
        """Run a task and handle completion/errors"""
        try:
            # Update drone state
            drone_state = self.state_manager.get_drone_state(drone_id)
            if drone_state:
                drone_state.current_task = task_id
                drone_state.task_status = "IN_PROGRESS"
            
            # Execute the task
            result = await task.execute()
            
            # Update completion status
            if drone_state:
                drone_state.task_status = "COMPLETED" if result else "FAILED"
                drone_state.current_task = None
            
            # Remove from active tasks
            if drone_id in self.active_tasks:
                del self.active_tasks[drone_id]
                
            self.logger.info(f"Task {task_id} completed with result: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {e}")
            
            # Update error status
            drone_state = self.state_manager.get_drone_state(drone_id)
            if drone_state:
                drone_state.task_status = "ERROR"
                drone_state.current_task = None
            
            # Remove from active tasks
            if drone_id in self.active_tasks:
                del self.active_tasks[drone_id]
            return False
    
    async def stop_task(self, drone_id: str) -> bool:
        """Stop the current task on the specified drone"""
        try:
            if drone_id not in self.active_tasks:
                return True
            
            # Get the drone connector
            connector = self.drone_connectors.get(drone_id)
            if not connector:
                return False
            
            # Send RTL (Return to Launch) command for safety
            await connector.return_to_launch()
            
            # Update state
            drone_state = self.state_manager.get_drone_state(drone_id)
            if drone_state:
                drone_state.task_status = "CANCELLED"
                drone_state.current_task = None
            
            # Remove from active tasks
            del self.active_tasks[drone_id]
            
            self.logger.info(f"Stopped task on drone {drone_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop task on drone {drone_id}: {e}")
            return False
    
    async def get_drone_status(self, drone_id: str) -> Optional[dict]:
        """Get current status of a specific drone"""
        drone_state = self.state_manager.get_drone_state(drone_id)
        if not drone_state:
            return None
        
        connector = self.drone_connectors.get(drone_id)
        if connector:
            # Get real-time telemetry
            telemetry = await connector.get_telemetry()
            return {
                "drone_id": drone_id,
                "status": drone_state.status,
                "position": telemetry.get("position"),
                "battery": telemetry.get("battery"),
                "armed": telemetry.get("armed", False),
                "current_task": drone_state.current_task,
                "task_status": drone_state.task_status,
                "last_update": drone_state.last_update.isoformat()
            }
        
        return drone_state.to_dict()
    
    async def _health_monitor(self):
        """Monitor system health and drone connections"""
        while self.is_running:
            try:
                # Check drone connections
                for drone_id, connector in self.drone_connectors.items():
                    if not connector.is_connected:
                        self.logger.warning(f"Drone {drone_id} disconnected, attempting reconnect...")
                        try:
                            await connector.reconnect()
                            self.logger.info(f"Reconnected to drone {drone_id}")
                        except Exception as e:
                            self.logger.error(f"Failed to reconnect to drone {drone_id}: {e}")
                
                # Update metrics
                self.metrics.update_connection_count(len(self.drone_connectors))
                self.metrics.update_active_tasks(len(self.active_tasks))
                
                await asyncio.sleep(self.config.health_check_interval)
                
            except Exception as e:
                self.logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(5) 