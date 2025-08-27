"""
Task Manager - Watches for tasks from Lattice and coordinates execution
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import random

class TaskManager:
    """
    Manages task watching from Lattice and coordinates task execution on drones
    """
    
    def __init__(self, lattice_connector, middleware):
        self.lattice_connector = lattice_connector
        self.middleware = middleware
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        
        # Task tracking
        self.active_tasks: Dict[str, Any] = {}  # task_id -> task_info
        
        # Retry configuration
        self.max_retries = 3
        self.base_retry_delay = 1.0  # seconds
        self.max_retry_delay = 60.0  # seconds
        
    async def start_task_watcher(self):
        """Start watching for tasks from Lattice"""
        self.is_running = True
        self.logger.info("Starting Lattice task watcher")
        
        retry_count = 0
        
        while self.is_running:
            try:
                # Watch for tasks assigned to our drone entity_ids (REST v2 expects agent_selector entity_ids)
                try:
                    assignee_ids = list(self.middleware.drone_connectors.keys())
                except Exception:
                    assignee_ids = []
                self.logger.info(f"Starting task watch with assignees: {assignee_ids}")
                await self.lattice_connector.watch_tasks(self._handle_task, drone_ids=assignee_ids)
                retry_count = 0  # Reset on successful connection
                
            except Exception as e:
                retry_count += 1
                self.logger.error(f"Task watcher error (attempt {retry_count}): {e}")
                
                if retry_count > self.max_retries:
                    # Calculate exponential backoff with jitter
                    delay = min(
                        self.base_retry_delay * (2 ** (retry_count - self.max_retries)),
                        self.max_retry_delay
                    )
                    jitter = random.uniform(0, delay * 0.1)  # 10% jitter
                    total_delay = delay + jitter
                    
                    self.logger.info(f"Retrying task watcher in {total_delay:.1f} seconds...")
                    await asyncio.sleep(total_delay)
                else:
                    await asyncio.sleep(self.base_retry_delay)
    
    async def stop(self):
        """Stop the task watcher"""
        self.is_running = False
        self.logger.info("Stopping task watcher")
        
        # Cancel all active tasks
        for task_id in list(self.active_tasks.keys()):
            await self._cancel_task(task_id)
    
    async def _handle_task(self, task: Any):
        """Handle incoming task from Lattice"""
        try:
            # Handle cancellation requests from ListenAsAgent
            if getattr(task, 'cancel_request', None) is not None:
                cancel_req = task.cancel_request
                task_id = getattr(cancel_req, 'task_id', None) or getattr(cancel_req, 'taskId', None)
                if task_id:
                    self.logger.info(f"Received cancel request for task {task_id}")
                    await self._cancel_task(str(task_id))
                else:
                    self.logger.warning("CancelRequest received without task_id")
                return
            
            # Handle completion requests
            if getattr(task, 'complete_request', None) is not None:
                complete_req = task.complete_request
                task_id = getattr(complete_req, 'task_id', None) or getattr(complete_req, 'taskId', None)
                if task_id:
                    self.logger.info(f"Received complete request for task {task_id}")
                    if str(task_id) in self.active_tasks:
                        drone_id = self.active_tasks[str(task_id)].get("drone_id", "")
                        await self.lattice_connector.update_task_status(
                            str(task_id), 
                            "STATUS_DONE_OK", 
                            1.0,
                            author_entity_id=drone_id
                        )
                        del self.active_tasks[str(task_id)]
                else:
                    self.logger.warning("CompleteRequest received without task_id")
                return

            # Extract task details from execute request
            task_id = None
            task_type = None
            target_entity = None
            spec_url = None
            
            # Handle REST v2 AgentRequest format
            if getattr(task, 'execute_request', None) is not None:
                exec_req = task.execute_request
                
                # Extract task_id
                try:
                    version_obj = getattr(getattr(exec_req, 'task', None), 'version', None)
                    task_id = getattr(version_obj, 'task_id', None)
                except Exception:
                    task_id = None
                
                # Extract specification URL
                try:
                    rest_task = getattr(exec_req, 'task', None)
                    spec = getattr(rest_task, 'specification', None)
                    spec_url = getattr(spec, 'type', None)
                except Exception:
                    spec_url = None
                
                # Extract assignee entity_id
                try:
                    rest_task = getattr(exec_req, 'task', None)
                    relations = getattr(rest_task, 'relations', None)
                    assignee = getattr(relations, 'assignee', None)
                    system = getattr(assignee, 'system', None)
                    target_entity = getattr(system, 'entity_id', None)
                except Exception:
                    target_entity = None
            else:
                # Fallback to legacy format (for testing)
                task_id = getattr(task, 'task_id', None)
                task_type = getattr(task, 'task_type', None)
                target_entity = getattr(task, 'target_entity_id', None)
            
            self.logger.info(f"Received task from Lattice: task_id={task_id}, spec_url={spec_url}, assignee={target_entity}")
            
            # Map specification URL to internal task type
            if not task_type and spec_url:
                if 'VisualId' in spec_url or 'Investigate' in spec_url or 'Monitor' in spec_url:
                    task_type = 'mapping'  # Default to mapping for surveillance tasks
                elif 'Mapping' in spec_url:
                    task_type = 'mapping'
                elif 'Relay' in spec_url:
                    task_type = 'relay'
                elif 'Dropping' in spec_url:
                    task_type = 'dropping'
                else:
                    task_type = 'mapping'  # Default fallback
            
            # Validate required fields
            if not task_id:
                self.logger.error("Task missing task_id")
                return
            
            if not target_entity:
                self.logger.error(f"Task {task_id} missing assignee entity_id")
                await self._reject_task(str(task_id), "Missing assignee entity_id")
                return
            
            # Check if target drone is available
            if target_entity not in self.middleware.drone_connectors:
                self.logger.error(f"Drone {target_entity} not available for task {task_id}")
                await self._reject_task(str(task_id), f"Drone {target_entity} not available")
                return
            
            # Store task information
            self.active_tasks[str(task_id)] = {
                "task": task,
                "drone_id": target_entity,
                "start_time": datetime.now(timezone.utc),
                "status": "ACCEPTED"
            }
            
            # Send acknowledgment sequence
            self.logger.info(f"Acknowledging task {task_id} for drone {target_entity}")
            await self.lattice_connector.update_task_status(
                str(task_id), 
                "STATUS_ACK", 
                0.0,
                author_entity_id=str(target_entity)
            )
            
            # Send WILCO to indicate ready to execute
            await asyncio.sleep(0.1)  # Small delay between status updates
            await self.lattice_connector.update_task_status(
                str(task_id), 
                "STATUS_WILCO", 
                0.0,
                author_entity_id=str(target_entity)
            )
            
            # Extract task parameters (if any)
            task_params = {}
            if hasattr(task, 'parameters'):
                task_params = getattr(task, 'parameters', {})
            
            # Execute task asynchronously
            self.logger.info(f"Starting execution of {task_type} task {task_id} on drone {target_entity}")
            asyncio.create_task(
                self._execute_task(
                    str(task_id), 
                    str(target_entity), 
                    str(task_type) if task_type else 'mapping', 
                    task_params
                )
            )
            
        except Exception as e:
            self.logger.error(f"Error handling task: {e}", exc_info=True)
            # Try to extract task_id for rejection
            task_id_safe = None
            try:
                if getattr(task, 'execute_request', None) is not None:
                    exec_req = task.execute_request
                    version_obj = getattr(getattr(exec_req, 'task', None), 'version', None)
                    task_id_safe = getattr(version_obj, 'task_id', None)
            except Exception:
                task_id_safe = getattr(task, 'task_id', None)
            
            if task_id_safe:
                await self._reject_task(str(task_id_safe), str(e))
    
    def _validate_task(self, task: Any) -> bool:
        """Validate incoming task parameters"""
        try:
            # Check required fields
            # For REST AgentRequest with execute_request, fields live under execute_request.task
            if getattr(task, 'execute_request', None) is not None:
                exec_req = task.execute_request
                rest_task = getattr(exec_req, 'task', None)
                version = getattr(rest_task, 'version', None)
                task_id = getattr(version, 'task_id', None)
                if not task_id:
                    return False
                # Accept REST tasks without enforcing our internal task_type/params
                return True
            else:
                if not hasattr(task, 'task_id') or not task.task_id:
                    return False
                if not hasattr(task, 'task_type') or not task.task_type:
                    return False
                if not hasattr(task, 'target_entity_id') or not task.target_entity_id:
                    return False
            
            # Validate task type
            valid_task_types = ["mapping", "relay", "dropping"]
            if hasattr(task, 'task_type') and task.task_type and task.task_type not in valid_task_types:
                self.logger.warning(f"Unrecognized internal task type: {getattr(task, 'task_type', None)} — accepting as generic")
                return True
            
            # Validate task-specific parameters
            if task.task_type == "mapping":
                params = task.parameters
                if not params.get("area_center") or not params.get("area_size"):
                    self.logger.error("Mapping task missing required parameters")
                    return False
                    
            elif getattr(task, 'task_type', None) == "relay":
                params = task.parameters
                if not params.get("relay_position"):
                    self.logger.error("Relay task missing relay position")
                    return False
                    
            elif getattr(task, 'task_type', None) == "dropping":
                params = task.parameters
                if not params.get("drop_locations"):
                    self.logger.error("Dropping task missing drop locations")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Task validation error: {e}")
            return False
    
    async def _execute_task(self, task_id: str, drone_id: str, task_type: str, task_params: Dict[str, Any]):
        """Execute a task on the specified drone"""
        try:
            self.logger.info(f"Executing {task_type} task {task_id} on drone {drone_id}")

            # Update task status to in progress using the proper StateManager method
            await self.lattice_connector.update_task_status(task_id, "STATUS_EXECUTING", 0.0, author_entity_id=drone_id)
            self.active_tasks[task_id]["status"] = "IN_PROGRESS"

            # CRITICAL FIX: Use StateManager's update_task_status method instead of direct assignment
            # This ensures thread-safe updates and proper state propagation to EntityManager
            self.middleware.state_manager.update_task_status(
                drone_id=drone_id,
                task_id=task_id,
                status="EXECUTING",
                progress=0.0,
            )
            self.logger.debug(f"Updated drone state for {drone_id} with task {task_id} via StateManager")

            # Create progress reporter that also updates StateManager
            progress_reporter = self._create_progress_reporter(task_id, drone_id)

            # Add progress reporter to task params
            task_params["progress_callback"] = progress_reporter

            # Execute task through middleware
            success = await self.middleware.execute_task(drone_id, task_type, task_params)

            if success:
                # Update task status to completed
                await self.lattice_connector.update_task_status(task_id, "STATUS_DONE_OK", 1.0, author_entity_id=drone_id)
                self.active_tasks[task_id]["status"] = "COMPLETED"
                # Update StateManager
                self.middleware.state_manager.update_task_status(drone_id, None, "COMPLETED", 1.0)
                self.logger.info(f"Task {task_id} completed successfully")
            else:
                # Map to Lattice v2 not ok
                await self.lattice_connector.update_task_status(task_id, "STATUS_DONE_NOT_OK", 0.0, author_entity_id=drone_id)
                self.active_tasks[task_id]["status"] = "FAILED"
                # Update StateManager
                self.middleware.state_manager.update_task_status(drone_id, None, "FAILED", 0.0)
                self.logger.error(f"Task {task_id} failed")

            # Clean up task record after delay
            await asyncio.sleep(60)  # Keep record for 1 minute
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]

        except Exception as e:
            self.logger.error(f"Task execution error for {task_id}: {e}")
            await self.lattice_connector.update_task_status(task_id, "STATUS_DONE_NOT_OK", 0.0, author_entity_id=drone_id)
            if task_id in self.active_tasks:
                self.active_tasks[task_id]["status"] = "FAILED"
            # Update StateManager even on error
            self.middleware.state_manager.update_task_status(drone_id, None, "FAILED", 0.0)
    
    def _create_progress_reporter(self, task_id: str, drone_id: str):
        """Create a progress reporting callback for tasks"""
        async def report_progress(progress: float, message: str = ""):
            try:
                # Update StateManager with progress
                self.middleware.state_manager.update_task_status(
                    drone_id=drone_id,
                    task_id=task_id,
                    status="EXECUTING",
                    progress=progress,
                )

                # If drone disarmed mid-task, auto fail the task
                try:
                    connector = self.middleware.drone_connectors.get(drone_id)
                    if connector is not None:
                        tel = await connector.get_telemetry()
                        if tel and tel.get("armed") is False:
                            await self.lattice_connector.update_task_status(
                                task_id,
                                "STATUS_DONE_NOT_OK",
                                0.0,
                                author_entity_id=drone_id,
                            )
                            if task_id in self.active_tasks:
                                self.active_tasks[task_id]["status"] = "FAILED"
                            # Update StateManager
                            self.middleware.state_manager.update_task_status(drone_id, None, "FAILED", 0.0)
                            return
                except Exception:
                    pass

                await self.lattice_connector.update_task_status(
                    task_id,
                    "STATUS_EXECUTING",
                    progress,
                    author_entity_id=drone_id,
                )
                if message:
                    self.logger.debug(f"Task {task_id} progress: {progress*100:.1f}% - {message}")
            except Exception as e:
                self.logger.error(f"Failed to report progress for task {task_id}: {e}")

        return report_progress
    
    async def _reject_task(self, task_id: str, reason: str):
        """Reject a task with reason"""
        try:
            self.logger.warning(f"Rejecting task {task_id}: {reason}")
            if not task_id:
                self.logger.error("Reject requested without task_id; cannot update status")
                return
            # Use the tracked drone_id if available
            author_entity_id = self.active_tasks.get(task_id, {}).get("drone_id", "")
            await self.lattice_connector.update_task_status(task_id, "STATUS_DONE_NOT_OK", 0.0, author_entity_id=author_entity_id)
        except Exception as e:
            self.logger.error(f"Failed to reject task {task_id}: {e}")
    
    async def _cancel_task(self, task_id: str):
        """Cancel an active task"""
        try:
            if not task_id:
                self.logger.error("Cancel requested without task_id")
                return
            if task_id not in self.active_tasks:
                return
            
            task_info = self.active_tasks[task_id]
            drone_id = task_info["drone_id"]
            
            # Stop task execution on drone
            await self.middleware.stop_task(drone_id)
            
            # Update task status (map cancel to DONE_NOT_OK)
            await self.lattice_connector.update_task_status(task_id, "STATUS_DONE_NOT_OK", 0.0, author_entity_id=drone_id)
            
            # Remove from active tasks
            del self.active_tasks[task_id]
            
            self.logger.info(f"Cancelled task {task_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to cancel task {task_id}: {e}")

    async def cancel_task(self, task_id: str) -> bool:
        """Public API to cancel a task by id (ensures task_id is provided)."""
        try:
            if not task_id:
                self.logger.error("Missing task_id for cancel_task")
                return False
            await self._cancel_task(task_id)
            return True
        except Exception as e:
            self.logger.error(f"cancel_task failed for {task_id}: {e}")
            return False
    
    def get_active_tasks(self) -> Dict[str, Any]:
        """Get information about all active tasks"""
        return {
            task_id: {
                "drone_id": info["drone_id"],
                "status": info["status"],
                "start_time": info["start_time"].isoformat(),
                "duration": (datetime.now(timezone.utc) - info["start_time"]).total_seconds()
            }
            for task_id, info in self.active_tasks.items()
        } 