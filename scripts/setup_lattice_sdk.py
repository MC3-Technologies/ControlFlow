#!/usr/bin/env python3
"""
Setup script for Lattice SDK and drone-api alignment
Run this after updating requirements.txt
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_environment():
    """Check if required environment variables are set"""
    required_vars = ['ENVIRONMENT_TOKEN', 'LATTICE_URL']
    optional_vars = ['SANDBOXES_TOKEN']
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.info("Please set these in your .env file or environment")
        return False
    
    logger.info("✓ Environment variables configured")
    
    # Check optional variables
    for var in optional_vars:
        if not os.getenv(var):
            logger.warning(f"Optional variable {var} not set - may be required for sandbox environments")
    
    return True


def install_dependencies():
    """Install Python dependencies"""
    logger.info("Installing Python dependencies...")
    
    try:
        # Upgrade pip first
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True)
        
        # Install main requirements
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements2.txt"], check=True)
        logger.info("✓ Dependencies installed successfully")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False
    
    return True


def install_lattice_sdk():
    """Attempt to install Lattice SDK from various sources"""
    logger.info("Attempting to install Lattice SDK...")
    
    # Method 1: Try PyPI first
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "anduril-lattice-sdk"], check=True)
        logger.info("✓ Lattice SDK installed from PyPI")
        return True
    except subprocess.CalledProcessError:
        logger.warning("Could not install from PyPI, trying alternative methods...")
    
    # Method 2: Try installing from Anduril's package repository
    try:
        # This URL would be provided by Anduril
        anduril_index = "https://packages.anduril.com/simple/"
        subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "--index-url", anduril_index,
            "anduril-lattice-sdk"
        ], check=True)
        logger.info("✓ Lattice SDK installed from Anduril repository")
        return True
    except:
        logger.warning("Could not install from Anduril repository")
    
    # Method 3: Check for local wheel file
    wheel_files = list(Path(".").glob("anduril*.whl"))
    if wheel_files:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", str(wheel_files[0])], check=True)
            logger.info(f"✓ Lattice SDK installed from local wheel: {wheel_files[0]}")
            return True
        except:
            logger.error(f"Failed to install from local wheel: {wheel_files[0]}")
    
    logger.error("""
    ❌ Could not install Lattice SDK automatically.
    
    Please contact your Anduril representative to get:
    1. The correct PyPI package name
    2. Access to Anduril's private package repository
    3. A wheel file for manual installation
    
    Once you have the SDK, install it using one of:
    - pip install anduril-lattice-sdk
    - pip install /path/to/anduril_lattice_sdk.whl
    """)
    
    return False


def verify_imports():
    """Verify that all required imports work"""
    logger.info("Verifying SDK imports...")
    
    try:
        # Test gRPC imports
        from grpclib.client import Channel
        logger.info("✓ gRPC imports successful")
        
        # Test Lattice SDK imports
        try:
            from anduril.entitymanager.v1 import EntityManagerApiStub, Entity
            from anduril.taskmanager.v1 import TaskManagerApiStub
            from anduril.tasks.v2 import TaskCatalog, TaskDefinition
            logger.info("✓ Lattice SDK imports successful")
            return True
        except ImportError as e:
            logger.warning(f"Lattice SDK imports failed: {e}")
            logger.info("Will use gRPC stubs as fallback")
            return True  # Continue with fallback
            
    except ImportError as e:
        logger.error(f"Critical import failed: {e}")
        return False


def test_lattice_connection():
    """Test connection to Lattice platform"""
    logger.info("Testing Lattice connection...")
    
    import asyncio
    from src.lattice_drone_control.connectors.lattice import LatticeConnector
    
    async def test():
        config = {
            'url': os.getenv('LATTICE_URL'),
            'use_grpc': True
        }
        
        connector = LatticeConnector(config)
        try:
            await connector.connect()
            logger.info("✓ Successfully connected to Lattice platform")
            await connector.disconnect()
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to Lattice: {e}")
            return False
    
    return asyncio.run(test())


def create_directories():
    """Create required directories"""
    dirs = ['logs', 'data', 'config']
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
    logger.info("✓ Created required directories")


def main():
    """Main setup process"""
    logger.info("=" * 60)
    logger.info("Lattice SDK Setup Script")
    logger.info("=" * 60)
    
    # Load .env file if it exists
    if Path(".env").exists():
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("✓ Loaded .env file")
    else:
        logger.warning("No .env file found - using system environment variables")
    
    # Run setup steps
    steps = [
        ("Checking environment", check_environment),
        ("Creating directories", create_directories),
        ("Installing dependencies", install_dependencies),
        ("Installing Lattice SDK", install_lattice_sdk),
        ("Verifying imports", verify_imports),
        ("Testing Lattice connection", test_lattice_connection)
    ]
    
    for step_name, step_func in steps:
        logger.info(f"\n{step_name}...")
        if not step_func():
            logger.error(f"Setup failed at: {step_name}")
            sys.exit(1)
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ Setup completed successfully!")
    logger.info("=" * 60)
    
    logger.info("""
    Next steps:
    1. Start SITL simulator (if testing locally):
       sim_vehicle.py -v ArduCopter -f quad --sysid 1 --out udp:YOUR_IP:14550
    
    2. Start MAVSDK server:
       ./start_mavsdk_server_minimal.bat
    
    3. Run the middleware:
       python -m src.lattice_drone_control.main --config config/default.yaml
    
    4. Check Lattice UI for your drone entity
    """)


if __name__ == "__main__":
    main()