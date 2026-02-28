'''
    Flight Tracker Package

    A Python application for tracking flights using FlightRadar24 API
    with Google Maps tile rendering and Tkinter GUI.
'''

import os
import sys

# Add package directory to path for backward compatibility
sys.path.append(os.path.dirname(__file__))

# Public API exports
from .config_manager import get_config, ConfigManager
from .flight_service import get_flight_service, FlightDataService
from .logger import get_logger

__all__ = [
    'get_config',
    'ConfigManager',
    'get_flight_service',
    'FlightDataService',
    'get_logger',
]

__version__ = '1.0.0'
