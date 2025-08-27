@echo off
REM Start MAVSDK Servers for Drone Swarm

echo Starting MAVSDK servers...

REM Start servers for 5 drones (use udpin:// to avoid deprecation warnings)
start "MAVSDK Server 1" mavsdk_server\mavsdk_server.exe -p 50040 udpin://0.0.0.0:14540
start "MAVSDK Server 2" mavsdk_server\mavsdk_server.exe -p 50041 udpin://0.0.0.0:14541
start "MAVSDK Server 3" mavsdk_server\mavsdk_server.exe -p 50042 udpin://0.0.0.0:14542
start "MAVSDK Server 4" mavsdk_server\mavsdk_server.exe -p 50043 udpin://0.0.0.0:14543
start "MAVSDK Server 5" mavsdk_server\mavsdk_server.exe -p 50044 udpin://0.0.0.0:14544

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
