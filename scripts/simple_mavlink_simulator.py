#!/usr/bin/env python3
"""
Simple MAVLink Simulator for Testing
Sends basic MAVLink messages to simulate a drone
"""

import time
import socket
import struct
import sys

class SimpleMavlinkSimulator:
    """Simple MAVLink message simulator"""
    
    def __init__(self, target_host='127.0.0.1', target_port=14540):
        self.target_host = target_host
        self.target_port = target_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sequence = 0
        self.system_id = 1
        self.component_id = 1
        
    def checksum(self, data):
        """Calculate MAVLink checksum"""
        crc = 0xFFFF
        for byte in data:
            tmp = byte ^ (crc & 0xFF)
            tmp = (tmp ^ (tmp << 4)) & 0xFF
            crc = (crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)
            crc = crc & 0xFFFF
        return crc
    
    def create_heartbeat(self):
        """Create MAVLink heartbeat message"""
        # MAVLink v1 header
        header = struct.pack('<BBBBBB',
            0xFE,  # Start marker
            9,     # Payload length
            self.sequence,
            self.system_id,
            self.component_id,
            0      # Message ID: HEARTBEAT
        )
        
        # Heartbeat payload
        payload = struct.pack('<IBBBBBB',
            0,     # custom_mode
            2,     # type: MAV_TYPE_QUADROTOR
            12,    # autopilot: MAV_AUTOPILOT_PX4
            0,     # base_mode
            0,     # system_status
            3      # mavlink_version
        )
        
        # Calculate checksum
        crc_data = header[1:] + payload + struct.pack('B', 50)  # CRC seed for heartbeat
        crc = self.checksum(crc_data)
        
        # Complete message
        message = header + payload + struct.pack('<H', crc)
        
        self.sequence = (self.sequence + 1) % 256
        return message
    
    def create_sys_status(self):
        """Create system status message"""
        # MAVLink v1 header
        header = struct.pack('<BBBBBB',
            0xFE,  # Start marker
            31,    # Payload length
            self.sequence,
            self.system_id,
            self.component_id,
            1      # Message ID: SYS_STATUS
        )
        
        # System status payload
        payload = struct.pack('<IIIHHHHHHHHHHH',
            0,      # onboard_control_sensors_present
            0,      # onboard_control_sensors_enabled
            0,      # onboard_control_sensors_health
            0,      # load
            12600,  # voltage_battery (mV)
            -1,     # current_battery (cA)
            75,     # battery_remaining (%)
            0,      # drop_rate_comm
            0,      # errors_comm
            0,      # errors_count1
            0,      # errors_count2
            0,      # errors_count3
            0       # errors_count4
        )
        
        # Calculate checksum
        crc_data = header[1:] + payload + struct.pack('B', 124)  # CRC seed for sys_status
        crc = self.checksum(crc_data)
        
        # Complete message
        message = header + payload + struct.pack('<H', crc)
        
        self.sequence = (self.sequence + 1) % 256
        return message
    
    def run(self):
        """Run the simulator"""
        print(f"Starting MAVLink simulator...")
        print(f"Sending to {self.target_host}:{self.target_port}")
        
        try:
            while True:
                # Send heartbeat
                heartbeat = self.create_heartbeat()
                self.sock.sendto(heartbeat, (self.target_host, self.target_port))
                
                # Send system status occasionally
                if self.sequence % 5 == 0:
                    sys_status = self.create_sys_status()
                    self.sock.sendto(sys_status, (self.target_host, self.target_port))
                
                print(f"Sent heartbeat (seq={self.sequence-1})")
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nSimulator stopped")
        finally:
            self.sock.close()

def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = 14540
    
    simulator = SimpleMavlinkSimulator(target_port=port)
    simulator.run()

if __name__ == "__main__":
    main() 