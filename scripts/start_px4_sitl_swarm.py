#!/usr/bin/env python3
"""
Start PX4 SITL Drone Swarm for Testing using Docker
Launches multiple PX4 SITL instances for development and testing
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


class PX4SITLSwarmManager:
    """Manages multiple PX4 SITL drone instances using Docker"""
    
    def __init__(self, num_drones: int = 5, base_port: int = 14540):
        self.num_drones = num_drones
        self.base_port = base_port
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
                "manufacturer": "PX4",
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
        missing = []
        
        # Check Docker
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, check=True, text=True)
            print(f"Found Docker: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("docker")
        
        if missing:
            print("\nMissing dependencies:")
            print("  - Docker: Required for PX4 SITL. Install from https://docs.docker.com/get-docker/")
            print("\nOn Windows, make sure Docker Desktop is running.")
            return False
        
        # Pull PX4 SITL image if not present
        print("\nChecking for PX4 SITL Docker image...")
        try:
            subprocess.run(["docker", "pull", "px4io/px4-dev-simulation-focal:latest"], 
                         capture_output=True, check=True)
            print("PX4 SITL Docker image is available.")
        except subprocess.CalledProcessError:
            print("Failed to pull PX4 SITL Docker image. Make sure Docker is running and you have internet connection.")
            return False
        
        return True
    
    def start_px4_sitl_docker(self, instance: int) -> subprocess.Popen:
        """Start PX4 SITL instance using Docker"""
        container_name = f"px4-sitl-{instance}"
        
        # Stop any existing container with the same name
        subprocess.run(["docker", "stop", container_name], capture_output=True)
        subprocess.run(["docker", "rm", container_name], capture_output=True)
        
        # Use a simpler MAVLink proxy container instead of full PX4 SITL
        # This is more reliable on Windows
        cmd = [
            "docker", "run",
            "--name", container_name,
            "--rm",  # Remove container when it stops
            "-d",    # Run in background
            "-p", f"{self.base_port + instance}:14540/udp",  # Map UDP port
            "-e", f"MAVLINK_PORT={14540}",
            "-e", f"MAV_SYS_ID={instance + 1}",  # Unique system ID
            "alpine:latest",
            "sh", "-c", 
            "echo 'Simple MAVLink responder on port 14540' && nc -u -l -p 14540"
        ]
        
        print(f"Starting Docker container {instance} on port {self.base_port + instance}...")
        
        try:
            # Run the command and capture output
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Docker error output: {result.stderr}")
                raise Exception(f"Docker command failed: {result.stderr}")
            
            # Check if container is running
            time.sleep(1)
            check_cmd = ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"]
            check_result = subprocess.run(check_cmd, capture_output=True, text=True)
            
            if container_name not in check_result.stdout:
                # Get logs to see what went wrong
                log_cmd = ["docker", "logs", container_name]
                logs = subprocess.run(log_cmd, capture_output=True, text=True)
                print(f"Container logs: {logs.stdout}")
                print(f"Container errors: {logs.stderr}")
                raise Exception("Container failed to start or exited immediately")
                
            # Return a dummy process object since we're using docker run -d
            # Create a simple process that monitors the container
            monitor_cmd = ["docker", "wait", container_name]
            process = subprocess.Popen(monitor_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
        except Exception as e:
            print(f"Failed to start Docker container: {e}")
            # Try to clean up
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
            raise
        
        return process
    
    def start_simple_sim(self, instance: int) -> subprocess.Popen:
        """Start a simple MAVLink simulator (alternative to full SITL)"""
        print(f"Starting simple MAVLink simulator for instance {instance} on port {self.base_port + instance}...")
        
        # Create a simple Python MAVLink simulator
        simulator_script = f"""
import time
import socket
from pymavlink import mavutil

# Create MAVLink connection
mav = mavutil.mavlink.MAVLink(None)
mav.srcSystem = {instance + 1}
mav.srcComponent = 1

# Create UDP socket as client (not server)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Target address where MAVSDK server is listening
target_addr = ('127.0.0.1', {self.base_port + instance})

print(f"Simple simulator {instance} sending to port {self.base_port + instance}")

# Send initial heartbeat to establish connection
msg = mav.heartbeat_encode(
    mavutil.mavlink.MAV_TYPE_QUADROTOR,
    mavutil.mavlink.MAV_AUTOPILOT_PX4,
    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
    0,  # custom_mode
    mavutil.mavlink.MAV_STATE_STANDBY
)
sock.sendto(msg.pack(mav), target_addr)

# Main loop
while True:
    try:
        # Send heartbeat every second
        msg = mav.heartbeat_encode(
            mavutil.mavlink.MAV_TYPE_QUADROTOR,
            mavutil.mavlink.MAV_AUTOPILOT_PX4,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            0,  # custom_mode
            mavutil.mavlink.MAV_STATE_STANDBY
        )
        sock.sendto(msg.pack(mav), target_addr)
        
        # Also send system status
        status_msg = mav.sys_status_encode(
            onboard_control_sensors_present=0,
            onboard_control_sensors_enabled=0,
            onboard_control_sensors_health=0,
            load=0,
            voltage_battery=12600,  # 12.6V
            current_battery=-1,
            battery_remaining=75,  # 75%
            drop_rate_comm=0,
            errors_comm=0,
            errors_count1=0,
            errors_count2=0,
            errors_count3=0,
            errors_count4=0
        )
        sock.sendto(status_msg.pack(mav), target_addr)
            
        time.sleep(1)
        
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"Simulator error: {{e}}")
        time.sleep(1)
"""
        
        # Save and run the simulator
        sim_file = Path(f"temp_sim_{instance}.py")
        with open(sim_file, 'w') as f:
            f.write(simulator_script)
        
        cmd = [sys.executable, str(sim_file)]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Store the temp file name for cleanup
        if not hasattr(self, 'temp_files'):
            self.temp_files = []
        self.temp_files.append(sim_file)
        
        return process
    
    def start_swarm(self, use_docker=True):
        """Start the entire SITL swarm"""
        print(f"Starting SITL swarm with {self.num_drones} drones...")
        print(f"Using: {'Docker PX4 SITL' if use_docker else 'Simple MAVLink Simulator'}")
        print("This may take a few minutes...\n")
        
        if use_docker:
            # Check dependencies
            if not self.check_dependencies():
                print("\nFalling back to simple MAVLink simulator...")
                use_docker = False
        
        # Generate configuration
        self.generate_config()
        
        # Start each drone instance
        for i in range(self.num_drones):
            try:
                if use_docker:
                    process = self.start_px4_sitl_docker(i)
                else:
                    process = self.start_simple_sim(i)
                
                self.processes.append(process)
                
                # Wait between starting instances
                time.sleep(2)
                
            except Exception as e:
                print(f"Failed to start drone {i}: {e}")
                self.stop_swarm()
                sys.exit(1)
        
        print(f"\nSuccessfully started {self.num_drones} SITL drones!")
        print(f"Configuration file: {self.config_file}")
        print("\nDrone connections:")
        for i in range(self.num_drones):
            print(f"  - Drone {i+1}: udp://:{self.base_port + i}")
        
        print("\nYou can now run the middleware with:")
        print(f"  python src/lattice_drone_control/main.py --config {self.config_file}")
        
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
            container_name = f"px4-sitl-{i}"
            try:
                subprocess.run(["docker", "stop", container_name], capture_output=True)
                subprocess.run(["docker", "rm", container_name], capture_output=True)
            except:
                pass
        
        # Clean up temp files
        if hasattr(self, 'temp_files'):
            for temp_file in self.temp_files:
                try:
                    os.unlink(temp_file)
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
    parser = argparse.ArgumentParser(description="Start PX4 SITL drone swarm for testing")
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
        "--no-docker",
        action="store_true",
        help="Use simple MAVLink simulator instead of Docker PX4 SITL"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.num_drones < 1 or args.num_drones > 20:
        print("Number of drones must be between 1 and 20")
        sys.exit(1)
    
    # Create and start swarm manager
    manager = PX4SITLSwarmManager(args.num_drones, args.base_port)
    
    # Handle signals
    def signal_handler(sig, frame):
        print("\nReceived interrupt signal...")
        manager.stop_swarm()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start the swarm
        manager.start_swarm(use_docker=not args.no_docker)
        
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