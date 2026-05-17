'''
    Centralized configuration management for Flight Tracker application.
    Uses dataclasses for type safety and default values.
'''

from dataclasses import dataclass, field
from configparser import ConfigParser
from pathlib import Path
from typing import Tuple, Optional
from logger import get_logger
from coords import LatLng

logger = get_logger(__name__)


@dataclass
class HomeConfig:
    """Home location and general settings."""
    latitude: float = 52.5162767
    longitude: float = 13.3777761
    zoom: int = 11
    timestep: float = 3.2
    locale_lang: str = 'en'
    locale_country: str = 'EN'

    @property
    def location(self) -> LatLng:
        """Return LatLng coordinate."""
        return LatLng(self.latitude, self.longitude)


@dataclass
class MapTilesConfig:
    """Map tile rendering settings."""
    basemap: str = 'terrain'  # terrain, satellite, roadmap
    roadmap: bool = False
    brightness: float = 0.4


@dataclass
class FlightTrackerConfig:
    """Configuration specific to FlightTracker application."""
    grid: Tuple[int, int] = (5, 5)
    map_tiles: MapTilesConfig = field(default_factory=MapTilesConfig)
    max_flight_age: int = 1200
    enable_rain_radar: bool = False
    enable_cloud_radar: bool = False
    enable_ekf: bool = True
    animation_rate: float = 5.0


@dataclass
class FollowFlightConfig:
    """Configuration specific to FollowFlight application."""
    grid: Tuple[int, int] = (4, 4)
    map_tiles: MapTilesConfig = field(default_factory=MapTilesConfig)
    centerview: bool = True
    max_trail: int = 150
    enable_rain_radar: bool = False
    enable_cloud_radar: bool = False
    enable_ekf: bool = True
    animation_rate: float = 5.0


@dataclass
class AppConfig:
    """Complete application configuration."""
    home: HomeConfig = field(default_factory=HomeConfig)
    flight_tracker: FlightTrackerConfig = field(default_factory=FlightTrackerConfig)
    follow_flight: FollowFlightConfig = field(default_factory=FollowFlightConfig)


class ConfigManager:
    """
    Centralized configuration manager.

    Usage:
        config_manager = ConfigManager()
        config = config_manager.load('config.ini')

        # Access configuration
        home_location = config.home.location
        grid = config.flight_tracker.grid
    """

    _instance: Optional['ConfigManager'] = None
    _config: Optional[AppConfig] = None

    def __new__(cls):
        """Singleton pattern - ensure only one config manager exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, config_path: str = 'config.ini') -> AppConfig:
        """
        Load configuration from INI file.

        Args:
            config_path: Path to configuration file

        Returns:
            AppConfig with all settings loaded
        """
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config file '{config_path}' not found, using defaults")
            self._config = AppConfig()
            return self._config

        parser = ConfigParser()
        parser.read(config_path)

        # Load home configuration
        home = self._load_home_config(parser)

        # Load app-specific configurations
        flight_tracker = self._load_flight_tracker_config(parser)
        follow_flight = self._load_follow_flight_config(parser)

        self._config = AppConfig(
            home=home,
            flight_tracker=flight_tracker,
            follow_flight=follow_flight
        )

        logger.debug(f"Configuration loaded from '{config_path}'")
        return self._config

    def get_config(self) -> AppConfig:
        """Get current configuration, loading defaults if not yet loaded."""
        if self._config is None:
            return self.load()
        return self._config

    def _load_home_config(self, parser: ConfigParser) -> HomeConfig:
        """Load HOME section from config."""
        config = HomeConfig()

        if 'HOME' not in parser:
            logger.warning("HOME section not found in config")
            return config

        section = parser['HOME']

        if 'latitude' in section and 'longitude' in section:
            config = HomeConfig(
                latitude=parser.getfloat('HOME', 'latitude'),
                longitude=parser.getfloat('HOME', 'longitude'),
                zoom=parser.getint('HOME', 'zoom') if 'zoom' in section else config.zoom,
                timestep=parser.getfloat('HOME', 'timestep') if 'timestep' in section else config.timestep,
                locale_lang=section.get('localeLang', config.locale_lang),
                locale_country=section.get('localeCountry', config.locale_country),
            )
        else:
            logger.warning("HOME config incomplete: latitude/longitude missing")

        return config

    def _load_map_tiles_config(self, parser: ConfigParser, section_name: str) -> MapTilesConfig:
        """Load map tiles settings from a config section."""
        config = MapTilesConfig()

        if section_name not in parser:
            return config

        section = parser[section_name]

        return MapTilesConfig(
            basemap=section.get('basemap', config.basemap),
            roadmap=parser.getboolean(section_name, 'roadmap') if 'roadmap' in section else config.roadmap,
            brightness=parser.getfloat(section_name, 'brightness') if 'brightness' in section else config.brightness,
        )

    def _parse_grid(self, grid_str: str, default: Tuple[int, int]) -> Tuple[int, int]:
        """Parse grid string 'X,Y' into tuple."""
        try:
            parts = grid_str.split(',')
            return (int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            logger.warning(f"Invalid grid format '{grid_str}', using default")
            return default

    def _load_flight_tracker_config(self, parser: ConfigParser) -> FlightTrackerConfig:
        """Load FlightTracker section from config."""
        config = FlightTrackerConfig()
        section_name = 'FlightTracker'

        if section_name not in parser:
            logger.warning(f"{section_name} section not found in config")
            return config

        section = parser[section_name]
        map_tiles = self._load_map_tiles_config(parser, section_name)

        return FlightTrackerConfig(
            grid=self._parse_grid(section.get('grid', ''), config.grid) if 'grid' in section else config.grid,
            map_tiles=map_tiles,
            max_flight_age=parser.getint(section_name, 'maxFlightAge') if 'maxFlightAge' in section else config.max_flight_age,
            enable_rain_radar=parser.getboolean(section_name, 'enableRainRadar') if 'enableRainRadar' in section else config.enable_rain_radar,
            enable_cloud_radar=parser.getboolean(section_name, 'enableCloudRadar') if 'enableCloudRadar' in section else config.enable_cloud_radar,
            enable_ekf=parser.getboolean(section_name, 'enableEkf') if 'enableEkf' in section else config.enable_ekf,
            animation_rate=parser.getfloat(section_name, 'animationRate') if 'animationRate' in section else config.animation_rate,
        )

    def _load_follow_flight_config(self, parser: ConfigParser) -> FollowFlightConfig:
        """Load FollowFlight section from config."""
        config = FollowFlightConfig()
        section_name = 'FollowFlight'

        if section_name not in parser:
            logger.warning(f"{section_name} section not found in config")
            return config

        section = parser[section_name]
        map_tiles = self._load_map_tiles_config(parser, section_name)

        return FollowFlightConfig(
            grid=self._parse_grid(section.get('grid', ''), config.grid) if 'grid' in section else config.grid,
            map_tiles=map_tiles,
            centerview=parser.getboolean(section_name, 'centerview') if 'centerview' in section else config.centerview,
            max_trail=parser.getint(section_name, 'maxtrail') if 'maxtrail' in section else config.max_trail,
            enable_rain_radar=parser.getboolean(section_name, 'enableRainRadar') if 'enableRainRadar' in section else config.enable_rain_radar,
            enable_cloud_radar=parser.getboolean(section_name, 'enableCloudRadar') if 'enableCloudRadar' in section else config.enable_cloud_radar,
            enable_ekf=parser.getboolean(section_name, 'enableEkf') if 'enableEkf' in section else config.enable_ekf,
            animation_rate=parser.getfloat(section_name, 'animationRate') if 'animationRate' in section else config.animation_rate,
        )


# Global config manager instance
_config_manager = ConfigManager()


def get_config(config_path: str = 'config.ini') -> AppConfig:
    """
    Convenience function to get application configuration.

    Usage:
        from config_manager import get_config
        config = get_config()
        print(config.home.location)
    """
    return _config_manager.load(config_path)
