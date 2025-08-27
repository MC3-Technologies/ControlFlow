"""
Prometheus metrics collection for monitoring
"""

import time
from typing import Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime
import logging

if TYPE_CHECKING:
    from prometheus_client import Histogram

try:
    from prometheus_client import Counter, Gauge, Histogram, Summary, Info
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Mock classes for when Prometheus is not available
    class MockMetric:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def inc(self, amount=1): pass
        def dec(self, amount=1): pass
        def set(self, value): pass
        def observe(self, value): pass
        def info(self, value): pass
        def time(self): return MockTimer()
    
    class MockTimer:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    
    Counter = Gauge = Histogram = Summary = Info = MockMetric

class MetricsCollector:
    """Collects and exposes metrics for Prometheus monitoring"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        if not PROMETHEUS_AVAILABLE:
            self.logger.warning("Prometheus client not available, metrics will be disabled")
        
        # Connection metrics
        self.drone_connections = Gauge(
            name='lattice_drone_connections_total',
            documentation='Total number of connected drones',
            labelnames=['status']
        )
        
        self.lattice_connection_status = Gauge(
            name='lattice_connection_status',
            documentation='Lattice platform connection status (1=connected, 0=disconnected)'
        )
        
        # Task metrics
        self.active_tasks = Gauge(
            name='lattice_active_tasks_total',
            documentation='Number of currently active tasks',
            labelnames=['task_type']
        )
        
        self.task_executions = Counter(
            name='lattice_task_executions_total',
            documentation='Total number of task executions',
            labelnames=['task_type', 'status']
        )
        
        self.task_duration = Histogram(
            name='lattice_task_duration_seconds',
            documentation='Task execution duration in seconds',
            labelnames=['task_type'],
            buckets=(10, 30, 60, 120, 300, 600, 1800, 3600)
        )
        
        # Telemetry metrics
        self.telemetry_updates = Counter(
            name='lattice_telemetry_updates_total',
            documentation='Total number of telemetry updates sent to Lattice',
            labelnames=['update_type', 'drone_id']
        )
        
        self.telemetry_latency = Histogram(
            name='lattice_telemetry_latency_seconds',
            documentation='Telemetry update latency in seconds',
            labelnames=['update_type'],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
        )
        
        # Drone state metrics
        self.drone_battery_level = Gauge(
            name='lattice_drone_battery_percent',
            documentation='Drone battery level percentage',
            labelnames=['drone_id']
        )
        
        self.drone_altitude = Gauge(
            name='lattice_drone_altitude_meters',
            documentation='Drone altitude in meters AGL',
            labelnames=['drone_id']
        )
        
        self.drone_armed_status = Gauge(
            name='lattice_drone_armed_status',
            documentation='Drone armed status (1=armed, 0=disarmed)',
            labelnames=['drone_id']
        )
        
        # Error metrics
        self.errors = Counter(
            name='lattice_errors_total',
            documentation='Total number of errors',
            labelnames=['error_type', 'component']
        )
        
        # System metrics
        self.system_info = Info(
            name='lattice_system_info',
            documentation='System information'
        )
        
        self.uptime = Gauge(
            name='lattice_uptime_seconds',
            documentation='Middleware uptime in seconds'
        )
        
        # Performance metrics (REST instead of gRPC)
        self.rest_request_duration = Histogram(
            name='lattice_rest_request_duration_seconds',
            documentation='REST (HTTP) request duration in seconds',
            labelnames=['endpoint'],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
        )
        
        self.mavlink_message_rate = Gauge(
            name='lattice_mavlink_message_rate_hz',
            documentation='MAVLink message rate in Hz',
            labelnames=['drone_id', 'message_type']
        )
        
        # Initialize system info
        self._start_time = time.time()
        self.update_system_info()
    
    def update_system_info(self, version: str = "1.0.0", environment: str = "development"):
        """Update system information metrics"""
        self.system_info.info({
            'version': version,
            'environment': environment,
            'prometheus_available': str(PROMETHEUS_AVAILABLE),
            'start_time': datetime.fromtimestamp(self._start_time).isoformat()
        })
    
    def update_connection_count(self, count: int, status: str = "connected"):
        """Update drone connection count"""
        self.drone_connections.labels(status=status).set(count)
    
    def update_lattice_connection(self, connected: bool):
        """Update Lattice connection status"""
        self.lattice_connection_status.set(1 if connected else 0)
    
    def update_active_tasks(self, count: int, task_type: str = "all"):
        """Update active task count"""
        self.active_tasks.labels(task_type=task_type).set(count)
    
    def record_task_execution(self, task_type: str, status: str):
        """Record a task execution"""
        self.task_executions.labels(task_type=task_type, status=status).inc()
    
    def record_task_duration(self, task_type: str, duration: float):
        """Record task execution duration"""
        self.task_duration.labels(task_type=task_type).observe(duration)
    
    def record_telemetry_update(self, update_type: str, drone_id: str):
        """Record telemetry update"""
        self.telemetry_updates.labels(update_type=update_type, drone_id=drone_id).inc()
    
    def record_telemetry_latency(self, update_type: str, latency: float):
        """Record telemetry update latency"""
        self.telemetry_latency.labels(update_type=update_type).observe(latency)
    
    def update_drone_metrics(self, drone_id: str, metrics: Dict[str, Any]):
        """Update drone-specific metrics"""
        if 'battery_percent' in metrics:
            self.drone_battery_level.labels(drone_id=drone_id).set(metrics['battery_percent'])
        
        if 'altitude' in metrics:
            self.drone_altitude.labels(drone_id=drone_id).set(metrics['altitude'])
        
        if 'armed' in metrics:
            self.drone_armed_status.labels(drone_id=drone_id).set(1 if metrics['armed'] else 0)
    
    def record_error(self, error_type: str, component: str):
        """Record an error occurrence"""
        self.errors.labels(error_type=error_type, component=component).inc()
    
    def update_uptime(self):
        """Update system uptime"""
        self.uptime.set(time.time() - self._start_time)
    
    def record_rest_request(self, endpoint: str, duration: float):
        """Record REST request duration"""
        self.rest_request_duration.labels(endpoint=endpoint).observe(duration)
    
    def update_mavlink_rate(self, drone_id: str, message_type: str, rate: float):
        """Update MAVLink message rate"""
        self.mavlink_message_rate.labels(drone_id=drone_id, message_type=message_type).set(rate)
    
    def time_operation(self, metric: Any, **labels):
        """Context manager for timing operations"""
        return metric.labels(**labels).time()
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of current metrics (for debugging/health checks)"""
        return {
            'uptime_seconds': time.time() - self._start_time,
            'prometheus_available': PROMETHEUS_AVAILABLE,
            'metrics': {
                'drone_connections': 0,  # Simplified for mock
                'active_tasks': 0,  # Simplified for mock
                'total_errors': 0  # Simplified for mock
            }
        } 