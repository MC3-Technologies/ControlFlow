#!/usr/bin/env python3
"""
Health check script for Lattice Drone Control Middleware
Verifies all components are operational
"""

import asyncio
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional

# Ensure project root is on PYTHONPATH so that `import src...` works regardless of
# where the script is launched from.
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lattice_drone_control.connectors.lattice import LatticeConnector
from src.lattice_drone_control.connectors.mavsdk import MAVSDKConnector
from src.lattice_drone_control.models.config import MiddlewareConfig, LatticeConfig, DroneConfig


class HealthChecker:
    """Performs comprehensive health checks on the middleware system"""
    
    def __init__(self, config_file: str = "config/default.yaml"):
        self.config_file = config_file
        self.results: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "UNKNOWN",
            "checks": {}
        }
    
    async def check_lattice_connection(self, lattice_config: Optional[LatticeConfig] = None) -> Dict[str, Any]:
        """Check Lattice platform connectivity"""
        result = {
            "status": "FAIL",
            "message": "",
            "latency_ms": None
        }
        
        try:
            import time
            start_time = time.time()
            
            # Use provided config or create default
            if lattice_config is None:
                lattice_config = LatticeConfig(
                    url="lattice.anduril.com",
                    use_grpc=True
                )
            connector = LatticeConnector(lattice_config)
            
            await connector.connect()
            await connector.disconnect()
            
            latency = (time.time() - start_time) * 1000
            result["status"] = "PASS"
            result["message"] = f"Lattice connection successful to {lattice_config.url}"
            result["latency_ms"] = round(latency, 2)
            
        except Exception as e:
            url = lattice_config.url if lattice_config else "unknown"
            result["message"] = f"Lattice connection failed to {url}: {type(e).__name__}: {str(e)}"
            
        return result
    
    async def check_drone_connections(self, drone_configs: List[DroneConfig]) -> Dict[str, Any]:
        """Check drone MAVLink connections"""
        results = {}
        
        for drone in drone_configs:
            drone_result = {
                "status": "FAIL",
                "message": "",
                "telemetry": None
            }
            
            try:
                connector = MAVSDKConnector(drone)
                await connector.connect()
                
                # Get telemetry to verify connection
                telemetry = await connector.get_telemetry()
                await connector.disconnect()
                
                drone_result["status"] = "PASS"
                drone_result["message"] = "Drone connected successfully"
                drone_result["telemetry"] = {
                    "battery": telemetry.get("battery", {}).get("remaining_percent", 0),
                    "armed": telemetry.get("armed", False),
                    "position": telemetry.get("position", {})
                }
                
            except Exception as e:
                drone_result["message"] = f"Connection failed: {str(e)}"
            
            results[drone.id] = drone_result
        
        return results
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Check system resource availability"""
        import psutil
        
        result = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "status": "PASS"
        }
        
        # Check if resources are within acceptable limits
        if result["cpu_percent"] > 90:
            result["status"] = "WARN"
            result["message"] = "High CPU usage"
        elif result["memory_percent"] > 90:
            result["status"] = "WARN"
            result["message"] = "High memory usage"
        elif result["disk_percent"] > 90:
            result["status"] = "WARN"
            result["message"] = "Low disk space"
        else:
            result["message"] = "System resources OK"
        
        return result
    
    def check_required_services(self) -> Dict[str, Any]:
        """Check if required services are running"""
        import subprocess
        import platform
        
        services_to_check = []
        results = {}
        
        if platform.system() == "Linux":
            # Check for Docker
            services_to_check.append(("docker", "systemctl is-active docker"))
            # Check for Prometheus (if configured)
            services_to_check.append(("prometheus", "systemctl is-active prometheus"))
        
        for service_name, check_cmd in services_to_check:
            try:
                result = subprocess.run(
                    check_cmd.split(),
                    capture_output=True,
                    text=True
                )
                results[service_name] = {
                    "status": "PASS" if result.returncode == 0 else "FAIL",
                    "message": result.stdout.strip()
                }
            except Exception as e:
                results[service_name] = {
                    "status": "SKIP",
                    "message": f"Cannot check: {str(e)}"
                }
        
        return results
    
    async def run_health_check(self) -> Dict[str, Any]:
        """Run all health checks"""
        import yaml
        
        # Load configuration
        try:
            with open(self.config_file, 'r') as f:
                config_data = yaml.safe_load(f)
                if not isinstance(config_data, dict):
                    raise ValueError("Configuration file must contain a dictionary")
                config = MiddlewareConfig.from_dict(config_data)
        except Exception as e:
            self.results["status"] = "ERROR"
            self.results["error"] = f"Failed to load config: {str(e)}"
            return self.results
        
        # Run checks
        print("Running health checks...")
        
        # 1. Lattice connectivity
        print("- Checking Lattice connection...")
        # Use lattice config from loaded configuration if available
        lattice_config = None
        if hasattr(config, 'lattice') and config.lattice:
            lattice_config = config.lattice
        self.results["checks"]["lattice"] = await self.check_lattice_connection(lattice_config)
        
        # 2. Drone connections
        print("- Checking drone connections...")
        self.results["checks"]["drones"] = await self.check_drone_connections(config.drones)
        
        # 3. System resources
        print("- Checking system resources...")
        self.results["checks"]["resources"] = self.check_system_resources()
        
        # 4. Required services
        print("- Checking required services...")
        self.results["checks"]["services"] = self.check_required_services()
        
        # Determine overall status
        all_passed = True
        has_warnings = False
        
        for check_name, check_result in self.results["checks"].items():
            if isinstance(check_result, dict):
                if check_result.get("status") == "FAIL":
                    all_passed = False
                elif check_result.get("status") == "WARN":
                    has_warnings = True
            else:
                # For drone checks (nested dict)
                for drone_id, drone_result in check_result.items():
                    if drone_result.get("status") == "FAIL":
                        all_passed = False
        
        if all_passed and not has_warnings:
            self.results["status"] = "HEALTHY"
        elif all_passed and has_warnings:
            self.results["status"] = "WARNING"
        else:
            self.results["status"] = "UNHEALTHY"
        
        return self.results


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Health check for Lattice Drone Middleware")
    parser.add_argument(
        "--config",
        default="config/default.yaml",
        help="Configuration file path"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously monitor health"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Check interval in seconds (for watch mode)"
    )
    
    args = parser.parse_args()
    
    checker = HealthChecker(args.config)
    
    if args.watch:
        # Continuous monitoring mode
        print(f"Starting health monitoring (interval: {args.interval}s)...")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                results = await checker.run_health_check()
                
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print(f"\nHealth Status: {results['status']}")
                    print(f"Timestamp: {results['timestamp']}")
                    
                    # Print summary
                    for check_name, check_result in results["checks"].items():
                        if check_name == "drones":
                            print(f"\nDrone Connections:")
                            for drone_id, drone_status in check_result.items():
                                print(f"  {drone_id}: {drone_status['status']}")
                        elif isinstance(check_result, dict):
                            print(f"\n{check_name.title()}: {check_result.get('status', 'UNKNOWN')}")
                            if check_result.get('message'):
                                print(f"  {check_result['message']}")
                
                print("\n" + "="*50)
                await asyncio.sleep(args.interval)
                
        except KeyboardInterrupt:
            print("\nHealth monitoring stopped.")
    else:
        # Single check mode
        results = await checker.run_health_check()
        
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\nHealth Check Results")
            print("=" * 50)
            print(f"Overall Status: {results['status']}")
            print(f"Timestamp: {results['timestamp']}")
            
            # Detailed results
            print("\nDetailed Results:")
            
            # Lattice
            lattice_check = results["checks"].get("lattice", {})
            print(f"\nLattice Connection: {lattice_check.get('status', 'UNKNOWN')}")
            if lattice_check.get('message'):
                print(f"  {lattice_check['message']}")
            if lattice_check.get('latency_ms'):
                print(f"  Latency: {lattice_check['latency_ms']}ms")
            
            # Drones
            drone_checks = results["checks"].get("drones", {})
            print(f"\nDrone Connections:")
            for drone_id, drone_status in drone_checks.items():
                print(f"  {drone_id}: {drone_status['status']}")
                if drone_status.get('telemetry'):
                    tel = drone_status['telemetry']
                    print(f"    Battery: {tel.get('battery', 0)}%")
                    print(f"    Armed: {tel.get('armed', False)}")
            
            # Resources
            resources = results["checks"].get("resources", {})
            print(f"\nSystem Resources: {resources.get('status', 'UNKNOWN')}")
            print(f"  CPU: {resources.get('cpu_percent', 0)}%")
            print(f"  Memory: {resources.get('memory_percent', 0)}%")
            print(f"  Disk: {resources.get('disk_percent', 0)}%")
            
            # Services
            services = results["checks"].get("services", {})
            if services:
                print(f"\nServices:")
                for service, status in services.items():
                    print(f"  {service}: {status['status']}")
        
        # Exit code based on status
        if results["status"] == "HEALTHY":
            sys.exit(0)
        elif results["status"] == "WARNING":
            sys.exit(1)
        else:
            sys.exit(2)


if __name__ == "__main__":
    # Install psutil if not present
    try:
        import psutil
    except ImportError:
        print("Installing required dependency: psutil")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
        import psutil
    
    asyncio.run(main()) 