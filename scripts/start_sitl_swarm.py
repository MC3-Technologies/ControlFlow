#!/usr/bin/env python3
"""
Start SITL Drone Swarm for Testing
Launch multiple ArduPilot SITL (ArduCopter) instances.

WSL/Windows guidance:
- When running in WSL and MAVSDK server runs on Windows, pass --windows-ip <IP>
  where <IP> is the Windows host IP visible from WSL:
    WINDOWS_IP=$(grep nameserver /etc/resolv.conf | awk '{print $2}')
    python scripts/start_sitl_swarm.py -n 2 --windows-ip $WINDOWS_IP
- Then in Windows PowerShell start matching MAVSDK servers:
    start "MAVSDK 1" mavsdk_server\mavsdk_server.exe -p 50040 udpin://0.0.0.0:14540
    start "MAVSDK 2" mavsdk_server\mavsdk_server.exe -p 50041 udpin://0.0.0.0:14541
"""

import subprocess
import time
import sys
import os
import signal
import argparse
import json
from typing import List, Dict, Any
from pathlib import Path


class SITLSwarmManager:
    """Manages multiple SITL drone instances"""
    
    def __init__(self, num_drones: int = 5, base_port: int = 14540, windows_ip: str | None = None):
        self.num_drones = num_drones
        self.base_port = base_port
        self.windows_ip = windows_ip
        self.processes: List[subprocess.Popen] = []
        self.config_file = Path("config/default.yaml")
        
    def generate_config(self):
        """Generate configuration for SITL swarm"""
        config = {
            # Direct MiddlewareConfig fields
            "service_name": "lattice-drone-middleware-sitl",
            "environment": "development",
            "log_level": "DEBUG",
            
            # Lattice configuration (optional for SITL)
            # "lattice": {
            #     "url": "lattice.anduril.com",
            #     "use_grpc": True,
            #     "bearer_token": "${LATTICE_BEARER_TOKEN}"
            # },
            
            # Drone configurations
            "drones": []
        }
        
        # Add drone configurations
        for i in range(self.num_drones):
            drone_config = {
                "id": f"sitl-drone-{i+1}",
                "connection_string": f"udp://:{self.base_port + i}",
                "type": "quadcopter",
                "manufacturer": "ArduPilot",
                "model": "SITL",
                "capabilities": ["mapping", "relay", "dropping"],
                "max_altitude": 120.0,
                "max_speed": 20.0,
                "max_flight_time": 1800,  # 30 minutes
                "geofence_enabled": True,
                "rtl_altitude": 50.0,
                "failsafe_action": "RTL"
            }
            config["drones"].append(drone_config)
        
        # Write config file
        import yaml
        self.config_file.parent.mkdir(exist_ok=True)
        with open(self.config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        print(f"Generated configuration: {self.config_file}")
        
    def check_dependencies(self):
        """Check if required dependencies are installed"""
        dependencies = {
            "docker": "Docker is required for PX4 SITL. Install from https://docs.docker.com/get-docker/",
            "jmavsim": "JMAVSim simulator. Part of PX4 installation."
        }
        
        missing = []
        
        # Check Docker
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("docker")
        
        if missing:
            print("Missing dependencies:")
            for dep in missing:
                print(f"  - {dep}: {dependencies.get(dep, '')}")
            return False
        
        return True
    
    def start_ardupilot_sitl(self, instance: int) -> subprocess.Popen:
        """Start ArduPilot SITL instance for CubePilot"""
        target_ip = self.windows_ip if self.windows_ip else "127.0.0.1"
        target = f"{target_ip}:{self.base_port + instance}"
        cmd = [
            "sim_vehicle.py",
            "-v", "ArduCopter",
            "-I", str(instance),
            "--out", target,
            "--no-extra-ports",
            "--model", "quad"
        ]
        
        print(
            f"Starting ArduPilot SITL instance {instance} sending MAVLink to {target}"
        )
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"Failed to start ArduPilot SITL: {e}")
            raise
        
        return process
    
    def start_mavsdk_server(self, instance: int) -> subprocess.Popen:
        """Start MAVSDK server for a drone instance"""
        cmd = [
            "docker", "run", "--rm",
            "-p", f"{50050 + instance}:{50050 + instance}",
            "--name", f"mavsdk-server-{instance}",
            "mavsdk/mavsdk-server:latest",
            f"udp://:{self.base_port + instance}",
            "-p", f"{50050 + instance}"
        ]
        
        print(f"Starting MAVSDK server for instance {instance} on port {50050 + instance}...")
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"Failed to start MAVSDK server: {e}")
            raise
        
        return process
    
    def start_swarm(self):
        """Start the entire SITL swarm"""
        print(f"Starting SITL swarm with {self.num_drones} drones...")
        print("This may take a few minutes...\n")
        
        # Check dependencies
        if not self.check_dependencies():
            print("\nPlease install missing dependencies and try again.")
            sys.exit(1)
        
        # Generate configuration
        self.generate_config()
        
        # Start each drone instance
        for i in range(self.num_drones):
            try:
                # Start ArduPilot SITL
                ardupilot_process = self.start_ardupilot_sitl(i)
                self.processes.append(ardupilot_process)
                
                # Wait for ArduPilot to initialize
                time.sleep(5)
                
                # Optional: Start MAVSDK server
                # mavsdk_process = self.start_mavsdk_server(i)
                # self.processes.append(mavsdk_process)
                
            except Exception as e:
                print(f"Failed to start drone {i}: {e}")
                self.stop_swarm()
                sys.exit(1)
        
        print(f"\nSuccessfully started {self.num_drones} SITL drones!")
        print(f"Configuration file: {self.config_file}")
        print("\nDrone connections:")
        for i in range(self.num_drones):
            print(f"  - Drone {i+1}: udp://:{self.base_port + i}")
        
        # Guidance for MAVSDK on Windows
        print("\nNext steps:")
        if self.windows_ip:
            print("  In Windows PowerShell, start matching MAVSDK servers:")
            for i in range(self.num_drones):
                udp_port = self.base_port + i
                grpc_port = 50040 + i
                print(
                    f"    start \"MAVSDK {i+1}\" mavsdk_server\\mavsdk_server.exe -p {grpc_port} udpin://0.0.0.0:{udp_port}"
                )
        else:
            print("  If MAVSDK server runs on Windows, rerun with --windows-ip <Windows_IP> so SITL sends to the host.")
            print("  Find the IP in WSL:")
            print("    WINDOWS_IP=$(grep nameserver /etc/resolv.conf | awk '{print $2}')")
            print("    python scripts/start_sitl_swarm.py -n", self.num_drones, "--windows-ip $WINDOWS_IP")
        
        print("\nPress Ctrl+C to stop the swarm...")
        
    def stop_swarm(self):
        """Stop all SITL instances"""
        print("\nStopping SITL swarm...")
        
        # Terminate all processes
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        
        # Stop Docker containers
        for i in range(self.num_drones):
            try:
                subprocess.run(["docker", "stop", f"px4-sitl-{i}"], capture_output=True)
                subprocess.run(["docker", "stop", f"mavsdk-server-{i}"], capture_output=True)
            except:
                pass
        
        print("SITL swarm stopped.")
    
    def monitor_swarm(self):
        """Monitor the health of SITL instances"""
        try:
            while True:
                time.sleep(10)
                
                # Check if all processes are still running
                dead_processes = []
                for i, process in enumerate(self.processes):
                    if process.poll() is not None:
                        dead_processes.append(i)
                
                if dead_processes:
                    print(f"\nWARNING: {len(dead_processes)} processes have died!")
                    for i in dead_processes:
                        print(f"  - Process {i} (return code: {self.processes[i].returncode})")
                
        except KeyboardInterrupt:
            pass


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Start SITL drone swarm for testing")
    parser.add_argument(
        "-n", "--num-drones",
        type=int,
        default=5,
        help="Number of drones to spawn (default: 5)"
    )
    parser.add_argument(
        "-p", "--base-port",
        type=int,
        default=14540,
        help="Base UDP port for drone connections (default: 14540)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (no GUI)"
    )
    parser.add_argument(
        "--gazebo",
        action="store_true",
        help="Use Gazebo simulator instead of JMAVSim"
    )
    parser.add_argument(
        "--windows-ip",
        type=str,
        default=None,
        help="Windows host IP to send MAVLink to (for WSL -> Windows routing). If omitted, uses 127.0.0.1"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.num_drones < 1 or args.num_drones > 20:
        print("Number of drones must be between 1 and 20")
        sys.exit(1)
    
    # Create and start swarm manager
    manager = SITLSwarmManager(args.num_drones, args.base_port, args.windows_ip)
    
    # Handle signals
    def signal_handler(sig, frame):
        print("\nReceived interrupt signal...")
        manager.stop_swarm()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start the swarm
        manager.start_swarm()
        
        # Monitor the swarm
        manager.monitor_swarm()
        
    except Exception as e:
        print(f"Error: {e}")
        manager.stop_swarm()
        sys.exit(1)
    finally:
        manager.stop_swarm()


if __name__ == "__main__":
    main() 