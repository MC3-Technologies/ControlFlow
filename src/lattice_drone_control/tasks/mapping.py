"""
Mapping task implementation for autonomous area mapping
"""

import asyncio
import math
from datetime import datetime
from typing import List, Tuple
from .base import BaseTask

class MappingTask(BaseTask):
    """
    Autonomous mapping task that flies a search pattern over a defined area
    
    Image Capture Implementation Notes:
    - The drone must have a camera gimbal connected via MAVLink
    - Camera triggering uses MAV_CMD_DO_DIGICAM_CONTROL or MAV_CMD_IMAGE_START_CAPTURE
    - Images are typically stored on the drone's companion computer or SD card
    - For production use, consider:
      - OpenCV for image processing
      - ExifRead for GPS tagging
      - Cloud storage integration (S3, Azure Blob)
      - Real-time streaming to Lattice if bandwidth permits
    """
    
    async def execute(self) -> bool:
        """Execute the mapping mission"""
        try:
            self.logger.info("Starting mapping task")
            self.is_running = True
            
            # Pre-flight checks
            if not await self.pre_flight_check():
                return False
            
            # Extract mapping parameters
            area_center = dict(self.params.get("area_center", {}))
            area_size = self.params.get("area_size", {"width": 100, "height": 100})  # meters
            altitude = self.params.get("altitude", 50)  # meters AGL
            overlap = self.params.get("overlap", 0.8)  # 80% overlap

            # If center not provided, fall back to current telemetry position
            if "lat" not in area_center or "lon" not in area_center:
                telemetry = await self.drone_connector.get_telemetry()
                pos = telemetry.get("position") or {}
                if not pos or "lat" not in pos or "lon" not in pos:
                    self.logger.error("No area_center provided and current position unavailable")
                    return False
                area_center["lat"] = float(pos["lat"])
                area_center["lon"] = float(pos["lon"])
                # Use relative altitude if available
                if "alt" not in area_center and "alt" in pos:
                    area_center["alt"] = float(pos["alt"])  # relative AGL from telemetry

            # Immediately takeoff after arming to avoid auto-disarm on idle
            # Ensures vehicle is airborne before goto commands
            self.logger.info(f"Takeoff to {altitude}m AGL for mapping task")
            if not await self.drone_connector.takeoff(altitude):
                self.logger.error("Takeoff failed; aborting mapping task")
                return False
            
            # Build waypoint path to draw the text "MC3" centered on area_center
            waypoints = self._generate_mc3_waypoints(
                center=area_center,
                size=area_size,
                altitude=altitude,
            )

            if not waypoints:
                self.logger.error("Failed to generate MC3 waypoints")
                return False

            # Navigate through waypoints
            self.logger.info(f"Flying MC3 pattern with {len(waypoints)} waypoints")
            for idx, wp in enumerate(waypoints):
                if not self.is_running:
                    self.logger.info("Mapping task stopped before completion")
                    break
                ok = await self.drone_connector.goto_position(wp["lat"], wp["lon"], wp["alt"])
                if not ok:
                    self.logger.warning(f"Failed to reach waypoint {idx+1}/{len(waypoints)}; continuing")
                await asyncio.sleep(0.5)

            self.logger.info("Returning to launch")
            rtl_ok = await self.drone_connector.return_to_launch()
            if not rtl_ok:
                self.logger.warning("RTL command failed or not supported; holding position")
                await self.drone_connector.hold_position()
            
            self.logger.info("Mapping task completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Mapping task failed: {e}")
            return False
        finally:
            self.is_running = False
    
    async def stop(self):
        """Stop the mapping task"""
        self.is_running = False
        await self.drone_connector.hold_position()
    
    def _generate_mc3_waypoints(self, center: dict, size: dict, altitude: float) -> List[dict]:
        """Generate waypoints to draw the letters "MC3" on the ground.

        The letters are constructed from straight-line strokes in meters and
        then converted to latitude/longitude offsets relative to the provided center.

        Args:
            center: dict with keys lat, lon.
            size: dict with keys width, height (meters) representing the overall bounding box for the text.
            altitude: target flight altitude (meters AGL).

        Returns:
            List of waypoints dicts: {lat, lon, alt}
        """
        try:
            lat_center = float(center["lat"])  # type: ignore[index]
            lon_center = float(center["lon"])  # type: ignore[index]
        except Exception:
            return []

        width_m = float(size.get("width", 100.0))
        height_m = float(size.get("height", 100.0))

        # Letter sizing and spacing
        # width = aspect_ratio * letter_height
        letter_aspect_ratio = 0.7
        spacing_ratio = 0.25  # spacing as a fraction of letter_height

        # Fit letters horizontally within width
        # total_width = 3 * (aspect*H) + 2 * (spacing*H) = H * (3*aspect + 2*spacing)
        denom = (3.0 * letter_aspect_ratio) + (2.0 * spacing_ratio)
        if denom <= 0.0:
            return []
        letter_height = min(height_m, width_m / denom)
        letter_width = letter_aspect_ratio * letter_height
        spacing_m = spacing_ratio * letter_height

        total_text_width = (3.0 * letter_width) + (2.0 * spacing_m)
        # Left edge of text block relative to center
        left_x = -total_text_width / 2.0

        # Helper to convert (x_m, y_m) offsets to lat/lon at constant altitude
        lat_deg_per_m = 1.0 / 111000.0
        lon_deg_per_m = 1.0 / (111000.0 * math.cos(math.radians(lat_center))) if math.cos(math.radians(lat_center)) != 0 else 0.0

        def to_waypoint(x_m: float, y_m: float) -> dict:
            return {
                "lat": lat_center + (y_m * lat_deg_per_m),
                "lon": lon_center + (x_m * lon_deg_per_m),
                "alt": float(altitude),
            }

        waypoints: List[dict] = []

        # Letter centers along X axis
        m_center_x = left_x + (letter_width / 2.0)
        c_center_x = m_center_x + (letter_width / 2.0) + spacing_m + (letter_width / 2.0)
        three_center_x = c_center_x + (letter_width / 2.0) + spacing_m + (letter_width / 2.0)

        # Baseline Y references (origin at text center):
        top_y = letter_height / 2.0
        bottom_y = -letter_height / 2.0

        # Construct M using strokes: BL -> TL -> mid-bottom -> TR -> BR
        def strokes_M(cx: float) -> List[Tuple[float, float]]:
            half_w = letter_width / 2.0
            return [
                (cx - half_w, bottom_y),
                (cx - half_w, top_y),
                (cx, bottom_y),
                (cx + half_w, top_y),
                (cx + half_w, bottom_y),
            ]

        # Construct C as a U-shape open on the right: TR -> TL -> BL -> BR
        def strokes_C(cx: float) -> List[Tuple[float, float]]:
            half_w = letter_width / 2.0
            return [
                (cx + half_w, top_y),
                (cx - half_w, top_y),
                (cx - half_w, bottom_y),
                (cx + half_w, bottom_y),
            ]

        # Construct 3 using a polyline approximation
        # TL -> TR -> mid-right-upper -> mid-center -> mid-right-lower -> BR -> BL
        def strokes_3(cx: float) -> List[Tuple[float, float]]:
            half_w = letter_width / 2.0
            quarter_h = letter_height / 4.0
            return [
                (cx - half_w, top_y),
                (cx + half_w, top_y),
                (cx + half_w, quarter_h),
                (cx, 0.0),
                (cx + half_w, -quarter_h),
                (cx + half_w, bottom_y),
                (cx - half_w, bottom_y),
            ]

        all_points: List[Tuple[float, float]] = []
        all_points.extend(strokes_M(m_center_x))
        # Small hop to start of next letter to avoid long diagonal draw within the letter spacing
        all_points.extend(strokes_C(c_center_x))
        all_points.extend(strokes_3(three_center_x))

        for (x_m, y_m) in all_points:
            waypoints.append(to_waypoint(x_m, y_m))

        return waypoints

    def _calculate_mapping_waypoints(
        self, 
        center: dict, 
        size: dict, 
        altitude: float, 
        overlap: float
    ) -> List[dict]:
        """Calculate waypoints for lawn mower search pattern"""
        
        waypoints = []
        
        # Convert size from meters to degrees (approximate)
        lat_deg_per_m = 1 / 111000  # Approximate conversion
        lon_deg_per_m = 1 / (111000 * math.cos(math.radians(center["lat"])))
        
        width_deg = size["width"] * lon_deg_per_m
        height_deg = size["height"] * lat_deg_per_m
        
        # Calculate flight line spacing based on overlap
        camera_fov = self.params.get("camera_fov", 30)  # meters ground coverage
        line_spacing = camera_fov * (1 - overlap)
        spacing_deg = line_spacing * lat_deg_per_m
        
        # Generate lawn mower pattern
        start_lat = center["lat"] - height_deg / 2
        end_lat = center["lat"] + height_deg / 2
        start_lon = center["lon"] - width_deg / 2
        end_lon = center["lon"] + width_deg / 2
        
        current_lat = start_lat
        going_east = True
        
        while current_lat <= end_lat:
            if going_east:
                waypoints.append({
                    "lat": current_lat,
                    "lon": start_lon,
                    "alt": altitude
                })
                waypoints.append({
                    "lat": current_lat,
                    "lon": end_lon,
                    "alt": altitude
                })
            else:
                waypoints.append({
                    "lat": current_lat,
                    "lon": end_lon,
                    "alt": altitude
                })
                waypoints.append({
                    "lat": current_lat,
                    "lon": start_lon,
                    "alt": altitude
                })
            
            current_lat += spacing_deg
            going_east = not going_east
        
        return waypoints
    
    async def _capture_mapping_data(self, waypoint: dict):
        """Disabled camera capture per request."""
        self.logger.info("Camera capture disabled by configuration")