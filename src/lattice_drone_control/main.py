"""
Lattice-Native Drone Control Middleware
Entry point for the middleware service that bridges Lattice platform with drone flight controllers
"""

import asyncio
import logging
import logging.handlers
import os
import signal
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import yaml

from .core.middleware import DroneMiddleware
from .utils.logging import setup_logging
from .models.config import MiddlewareConfig
from dotenv import load_dotenv

async def main():
    """Main entry point for the middleware service"""
    
    # Load environment variables from .env if present
    try:
        load_dotenv()
    except Exception:
        pass

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Lattice-Native Drone Control Middleware')
    parser.add_argument('--config', type=str, default='config/default.yaml',
                        help='Path to configuration file (default: config/default.yaml)')
    args = parser.parse_args()
    
    # Setup logging to file
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create a timestamp for the log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"lattice_drone_{timestamp}.log"
    
    # Configure root logger: clear any existing handlers (including console)
    root_logger = logging.getLogger()
    # Allow env override for log level to reduce INFO noise
    env_level = os.getenv("DRONE_LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, env_level, logging.INFO)
    root_logger.setLevel(numeric_level)
    try:
        for h in list(root_logger.handlers):
            root_logger.removeHandler(h)
    except Exception:
        pass
    
    # Create file handler with rotation (10MB per file, keep 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(numeric_level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    # Add handler to root logger
    root_logger.addHandler(file_handler)

    # Ensure noisy third-party loggers don't attach their own console handlers
    for noisy in ("httpx", "grpclib", "urllib3"):
        lg = logging.getLogger(noisy)
        try:
            for h in list(lg.handlers):
                lg.removeHandler(h)
        except Exception:
            pass
        # Reduce HTTP client verbosity
        if noisy == "httpx":
            lg.setLevel(logging.WARNING)
        lg.propagate = True
    
    # Do not add console handler; logs only to file per request
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting Lattice Drone Control Middleware - Logging to: {log_file}")
    logger.info(f"Log level: {env_level}")
    
    # Load configuration
    try:
        with open(args.config, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Ensure config_data is a dictionary before unpacking
        if not isinstance(config_data, dict):
            raise ValueError(f"Configuration file must contain a dictionary, got {type(config_data)}")
        
        config = MiddlewareConfig.from_dict(config_data)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # Initialize middleware
    middleware = DroneMiddleware(config)
    
    # Setup graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, stopping middleware...")
        asyncio.create_task(middleware.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start the middleware service
        await middleware.start()
        logger.info("Middleware started successfully")
        
        # Keep running until shutdown
        while middleware.is_running:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Middleware failed: {e}")
        sys.exit(1)
    finally:
        await middleware.shutdown()
        logger.info("Middleware stopped")

if __name__ == "__main__":
    asyncio.run(main()) 