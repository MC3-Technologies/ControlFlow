"""
Structured logging configuration for the middleware
"""

import logging
import sys
import json
from datetime import datetime
from typing import Dict, Any
import traceback

class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        drone_id = getattr(record, 'drone_id', None)
        if drone_id:
            log_data['drone_id'] = drone_id
        
        task_id = getattr(record, 'task_id', None)
        if task_id:
            log_data['task_id'] = task_id
            
        task_type = getattr(record, 'task_type', None)
        if task_type:
            log_data['task_type'] = task_type
        
        # Add exception info if present
        if record.exc_info:
            exc_type = record.exc_info[0]
            log_data['exception'] = {
                'type': exc_type.__name__ if exc_type else 'Unknown',
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_data)

class ColoredFormatter(logging.Formatter):
    """Colored console formatter for development"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors"""
        levelname = record.levelname
        if levelname in self.COLORS:
            levelname_color = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
            record.levelname = levelname_color
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        
        # Build log message
        log_format = f"{timestamp} - {record.levelname} - {record.name} - {record.getMessage()}"
        
        # Add drone_id if present
        drone_id = getattr(record, 'drone_id', None)
        if drone_id:
            log_format = f"{timestamp} - {record.levelname} - [{drone_id}] - {record.name} - {record.getMessage()}"
        
        return log_format

def setup_logging(log_level: str = "INFO", structured: bool = False, log_file: str | None = None):
    """
    Setup logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        structured: Use structured JSON logging
        log_file: Optional log file path
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Do not add console handler; logs will be file-only when log_file is provided
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_formatter = StructuredFormatter()  # Always use structured for files
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Set specific loggers
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('mavsdk').setLevel(logging.WARNING)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized at {log_level} level")

class DroneLogAdapter(logging.LoggerAdapter):
    """Logger adapter that adds drone context"""
    
    def __init__(self, logger: logging.Logger, drone_id: str):
        super().__init__(logger, {'drone_id': drone_id})
    
    def process(self, msg, kwargs):
        """Add drone_id to all log records"""
        extra = kwargs.get('extra', {})
        if self.extra:
            extra['drone_id'] = self.extra.get('drone_id', '')
        kwargs['extra'] = extra
        return msg, kwargs

class TaskLogAdapter(logging.LoggerAdapter):
    """Logger adapter that adds task context"""
    
    def __init__(self, logger: logging.Logger, task_id: str, task_type: str | None = None):
        super().__init__(logger, {'task_id': task_id, 'task_type': task_type})
    
    def process(self, msg, kwargs):
        """Add task context to all log records"""
        extra = kwargs.get('extra', {})
        if self.extra:
            extra['task_id'] = self.extra.get('task_id', '')
            task_type = self.extra.get('task_type')
            if task_type:
                extra['task_type'] = task_type
        kwargs['extra'] = extra
        return msg, kwargs 