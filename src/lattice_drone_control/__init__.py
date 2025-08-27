"""
Lattice-Native Drone Control System

A middleware solution for bridging Lattice mission command software with drone flight controllers
"""

__version__ = "1.0.0"
__author__ = "Ibrahim Matar"

from .core.middleware import DroneMiddleware
from .models.config import MiddlewareConfig

__all__ = ["DroneMiddleware", "MiddlewareConfig"] 