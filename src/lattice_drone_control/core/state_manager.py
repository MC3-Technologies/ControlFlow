"""
State Manager - Maintains current state of all connected drones
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from threading import RLock

class StateManager:
    """
    Thread-safe state management for all connected drones
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._lock = RLock()  # Reentrant lock for thread safety
        
        # Drone states - maps drone_id to DroneState
        self._drone_states: Dict[str, Any] = {}
        
        # State change callbacks
        self._state_change_callbacks = []
        
    def update_drone_state(self, drone_id: str, drone_state: Any):
        """Update the state of a specific drone"""
        with self._lock:
            # Check if this is a new drone or state change
            is_new = drone_id not in self._drone_states
            old_state = None if is_new else self._drone_states[drone_id]
            
            # Update state
            self._drone_states[drone_id] = drone_state
            drone_state.last_update = datetime.now(timezone.utc)
            
            # Log state change
            if is_new:
                self.logger.info(f"Added drone {drone_id} to state manager")
            else:
                # Check for significant state changes
                if old_state and hasattr(old_state, 'status') and hasattr(drone_state, 'status'):
                    if old_state.status != drone_state.status:
                        self.logger.info(f"Drone {drone_id} status changed: {old_state.status} -> {drone_state.status}")
                if old_state and hasattr(old_state, 'current_task') and hasattr(drone_state, 'current_task'):
                    if old_state.current_task != drone_state.current_task:
                        self.logger.info(f"Drone {drone_id} task changed: {old_state.current_task} -> {drone_state.current_task}")
            
            # Notify callbacks
            self._notify_state_change(drone_id, old_state, drone_state)
    
    def get_drone_state(self, drone_id: str) -> Optional[Any]:
        """Get the current state of a specific drone"""
        with self._lock:
            return self._drone_states.get(drone_id)
    
    def get_all_drone_states(self) -> Dict[str, Any]:
        """Get states of all drones"""
        with self._lock:
            return self._drone_states.copy()
    
    def remove_drone(self, drone_id: str):
        """Remove a drone from state management"""
        with self._lock:
            if drone_id in self._drone_states:
                old_state = self._drone_states[drone_id]
                del self._drone_states[drone_id]
                self.logger.info(f"Removed drone {drone_id} from state manager")
                
                # Notify callbacks of removal
                self._notify_state_change(drone_id, old_state, None)
    
    def update_telemetry(self, drone_id: str, telemetry_data: Dict[str, Any]):
        """Update telemetry data for a drone"""
        with self._lock:
            drone_state = self._drone_states.get(drone_id)
            if not drone_state:
                self.logger.warning(f"Attempted to update telemetry for unknown drone {drone_id}")
                return
            
            # Update position
            if "position" in telemetry_data:
                if not hasattr(drone_state, 'position'):
                    drone_state.position = type('Position', (), {})()
                setattr(drone_state.position, 'latitude', telemetry_data["position"].get("lat", 0.0))
                setattr(drone_state.position, 'longitude', telemetry_data["position"].get("lon", 0.0))
                setattr(drone_state.position, 'altitude', telemetry_data["position"].get("alt", 0.0))
            
            # Update battery
            if "battery" in telemetry_data:
                drone_state.battery_percent = telemetry_data["battery"].get("remaining_percent", 0)
                drone_state.battery_voltage = telemetry_data["battery"].get("voltage", 0.0)
            
            # Update armed status
            if "armed" in telemetry_data:
                drone_state.armed = telemetry_data["armed"]
            
            # Update timestamp
            drone_state.last_update = datetime.now(timezone.utc)
    
    def update_task_status(self, drone_id: str, task_id: Optional[str], status: str, progress: float = 0.0):
        """Update task execution status for a drone"""
        with self._lock:
            drone_state = self._drone_states.get(drone_id)
            if not drone_state:
                self.logger.warning(f"Attempted to update task status for unknown drone {drone_id}")
                return
            
            old_task = drone_state.current_task
            old_status = drone_state.task_status
            
            # Update task information
            drone_state.current_task = task_id
            drone_state.task_status = status
            drone_state.task_progress = progress
            drone_state.last_update = datetime.now(timezone.utc)

            # ADD THIS DEBUG LOGGING
            self.logger.info(
                f"StateManager updated drone {drone_id}: task={task_id}, status={status}, progress={progress:.2f}"
            )
            self.logger.debug(
                f"Drone state after update: current_task={drone_state.current_task}, task_status={drone_state.task_status}"
            )
            
            # Log task changes
            if old_task != task_id:
                self.logger.info(f"Drone {drone_id} task changed: {old_task} -> {task_id}")
            if old_status != status:
                self.logger.info(f"Drone {drone_id} task status: {status} ({progress*100:.1f}%)")
    
    def register_state_change_callback(self, callback):
        """Register a callback for state changes"""
        with self._lock:
            self._state_change_callbacks.append(callback)
    
    def _notify_state_change(self, drone_id: str, old_state: Any, new_state: Any):
        """Notify registered callbacks of state changes"""
        for callback in self._state_change_callbacks:
            try:
                callback(drone_id, old_state, new_state)
            except Exception as e:
                self.logger.error(f"State change callback error: {e}")
    
    def get_drone_count(self) -> int:
        """Get the number of drones being managed"""
        with self._lock:
            return len(self._drone_states)
    
    def get_active_drone_count(self) -> int:
        """Get the number of drones with active tasks"""
        with self._lock:
            return sum(1 for state in self._drone_states.values() 
                      if state.current_task is not None)
    
    def get_connected_drone_count(self) -> int:
        """Get the number of connected drones"""
        with self._lock:
            return sum(1 for state in self._drone_states.values() 
                      if state.status == "CONNECTED")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all drone states"""
        with self._lock:
            return {
                "total_drones": self.get_drone_count(),
                "connected_drones": self.get_connected_drone_count(),
                "active_drones": self.get_active_drone_count(),
                "drones": {
                    drone_id: {
                        "status": state.status,
                        "armed": getattr(state, 'armed', False),
                        "battery_percent": getattr(state, 'battery_percent', 0),
                        "current_task": state.current_task,
                        "task_status": state.task_status,
                        "last_update": state.last_update.isoformat()
                    }
                    for drone_id, state in self._drone_states.items()
                }
            } 