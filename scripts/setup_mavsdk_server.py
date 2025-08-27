#!/usr/bin/env python3
"""
Setup MAVSDK Server for Windows
Downloads and configures the MAVSDK server binary
"""

import os
import sys
import platform
import urllib.request
import zipfile
import json
import subprocess
from pathlib import Path


MAVSDK_RELEASES_URL = "https://api.github.com/repos/mavlink/MAVSDK/releases/latest"
MAVSDK_SERVER_DIR = Path("mavsdk_server")


def get_latest_release_info():
    """Get the latest MAVSDK release information"""
    print("Fetching latest MAVSDK release info...")
    
    try:
        with urllib.request.urlopen(MAVSDK_RELEASES_URL) as response:
            data = json.loads(response.read().decode())
            return data
    except Exception as e:
        print(f"Error fetching release info: {e}")
        sys.exit(1)


def download_mavsdk_server_windows():
    """Download MAVSDK server for Windows"""
    release_info = get_latest_release_info()
    
    # Find Windows binary
    windows_asset = None
    for asset in release_info['assets']:
        if 'mavsdk_server_win32.exe' in asset['name']:
            windows_asset = asset
            break
    
    if not windows_asset:
        print("Error: Could not find Windows MAVSDK server binary in latest release")
        print("Available assets:")
        for asset in release_info['assets']:
            print(f"  - {asset['name']}")
        sys.exit(1)
    
    # Create directory
    MAVSDK_SERVER_DIR.mkdir(exist_ok=True)
    
    # Download binary
    download_url = windows_asset['browser_download_url']
    filename = MAVSDK_SERVER_DIR / "mavsdk_server.exe"
    
    print(f"Downloading {windows_asset['name']}...")
    print(f"URL: {download_url}")
    
    try:
        urllib.request.urlretrieve(download_url, filename)
        print(f"Downloaded to: {filename}")
        return filename
    except Exception as e:
        print(f"Error downloading: {e}")
        sys.exit(1)


def create_start_script():
    """Create a batch script to start MAVSDK servers"""
    script_content = """@echo off
REM Start MAVSDK Servers for Drone Swarm

echo Starting MAVSDK servers...

REM Start servers for 5 drones
start "MAVSDK Server 1" mavsdk_server\\mavsdk_server.exe -p 50040 udp://:14540
start "MAVSDK Server 2" mavsdk_server\\mavsdk_server.exe -p 50041 udp://:14541
start "MAVSDK Server 3" mavsdk_server\\mavsdk_server.exe -p 50042 udp://:14542
start "MAVSDK Server 4" mavsdk_server\\mavsdk_server.exe -p 50043 udp://:14543
start "MAVSDK Server 5" mavsdk_server\\mavsdk_server.exe -p 50044 udp://:14544

echo MAVSDK servers started!
echo.
echo Server mappings:
echo   Drone on UDP 14540 -> MAVSDK server on port 50040
echo   Drone on UDP 14541 -> MAVSDK server on port 50041
echo   Drone on UDP 14542 -> MAVSDK server on port 50042
echo   Drone on UDP 14543 -> MAVSDK server on port 50043
echo   Drone on UDP 14544 -> MAVSDK server on port 50044
echo.
echo Press any key to stop all servers...
pause >nul

REM Kill all mavsdk_server processes
taskkill /F /IM mavsdk_server.exe
"""
    
    script_path = Path("start_mavsdk_servers.bat")
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    print(f"Created start script: {script_path}")
    return script_path


def create_start_script_minimal():
    """Create a batch script to start single MAVSDK server"""
    script_content = """@echo off
REM Start MAVSDK Server for Single Drone

echo Starting MAVSDK server...

mavsdk_server\\mavsdk_server.exe -p 50040 udp://:14540

"""
    
    script_path = Path("start_mavsdk_server_minimal.bat")
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    print(f"Created minimal start script: {script_path}")
    return script_path


def main():
    """Main setup function"""
    print("MAVSDK Server Setup for Windows")
    print("=" * 40)
    
    # Check if Windows
    if platform.system() != "Windows":
        print("This script is for Windows only!")
        sys.exit(1)
    
    # Check if already exists
    exe_path = MAVSDK_SERVER_DIR / "mavsdk_server.exe"
    if exe_path.exists():
        print(f"MAVSDK server already exists at: {exe_path}")
        response = input("Download again? (y/N): ")
        if response.lower() != 'y':
            print("Using existing server.")
            create_start_script()
            create_start_script_minimal()
            return
    
    # Download server
    server_path = download_mavsdk_server_windows()
    
    # Create start scripts
    create_start_script()
    create_start_script_minimal()
    
    print("\n" + "=" * 40)
    print("Setup complete!")
    print("\nTo use MAVSDK server:")
    print("1. For single drone: Run 'start_mavsdk_server_minimal.bat'")
    print("2. For drone swarm: Run 'start_mavsdk_servers.bat'")
    print("\nMake sure to start these BEFORE running the middleware!")


if __name__ == "__main__":
    main() 