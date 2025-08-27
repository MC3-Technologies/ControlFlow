@echo off
REM Start MAVSDK Server for Single Drone

echo Starting MAVSDK server...

mavsdk_server\mavsdk_server.exe -p 50050 udpin://0.0.0.0:14550

