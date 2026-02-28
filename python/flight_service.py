'''
    Flight Data Service - Centralizes all flight data access.
    Decouples UI components from API implementations.
'''

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any, Callable, TypeVar
from functools import wraps
import time
from FlightRadar24_patch.api import FlightRadar24API
from logger import get_logger
from constants import MAX_API_RETRIES, RETRY_DELAY_MS

logger = get_logger(__name__)

T = TypeVar('T')


def with_retry(
    max_retries: int = MAX_API_RETRIES,
    delay_ms: int = RETRY_DELAY_MS,
    default: Any = None
) -> Callable:
    """
    Decorator that adds retry logic to a function.

    Args:
        max_retries: Maximum number of retry attempts
        delay_ms: Delay between retries in milliseconds
        default: Default value to return if all retries fail

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.debug(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                        )
                        time.sleep(delay_ms / 1000.0)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
            return default
        return wrapper
    return decorator


@dataclass
class FlightPosition:
    """Immutable flight position data."""
    id: str
    timestamp: int
    latitude: float
    longitude: float
    altitude: int  # feet
    heading: int
    ground_speed: int  # knots
    callsign: Optional[str] = None
    aircraft_code: Optional[str] = None
    airline_icao: Optional[str] = None
    origin_iata: Optional[str] = None
    destination_iata: Optional[str] = None


@dataclass
class FlightDetails:
    """Extended flight information."""
    id: str
    callsign: Optional[str] = None
    aircraft_model: Optional[str] = None
    airline_name: Optional[str] = None
    origin_airport: Optional[str] = None
    destination_airport: Optional[str] = None
    first_timestamp: Optional[int] = None
    trail: List[Dict] = field(default_factory=list)
    raw_data: Dict = field(default_factory=dict)


class FlightDataService:
    """
    Centralized service for fetching flight data.

    This service abstracts away the FlightRadar24 API and provides
    a clean interface for the UI layer to fetch flight information.

    Usage:
        service = FlightDataService()
        flights = service.get_flights_in_bounds(bounds_str)
        details = service.get_flight_details(flight_id)
    """

    _instance: Optional['FlightDataService'] = None

    def __new__(cls, api: Optional[FlightRadar24API] = None):
        """Singleton pattern for shared service instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, api: Optional[FlightRadar24API] = None):
        """Initialize with optional API instance for testing."""
        if self._initialized:
            return
        self._api = api or FlightRadar24API()
        self._api.set_flight_tracker_config(vehicles=0)
        self._details_cache: Dict[str, FlightDetails] = {}
        self._initialized = True

    def get_flights_in_bounds(self, bounds: str) -> List[Any]:
        """
        Get all flights within the specified bounds.

        Args:
            bounds: Bounds string in format 'lat1,lat2,lng1,lng2'

        Returns:
            List of flight objects from API
        """
        return self._fetch_flights(bounds)

    @with_retry(default=[])
    def _fetch_flights(self, bounds: str) -> List[Any]:
        """Internal method with retry logic for fetching flights."""
        return self._api.get_flights(bounds=bounds)

    def get_flights_by_id(self, bounds: str, flight_id: str) -> List[Any]:
        """
        Get flights matching a specific flight ID.

        Args:
            bounds: Bounds string for search area
            flight_id: Flight ID to search for

        Returns:
            List of matching flight objects
        """
        return self._fetch_flights_by_id(bounds, flight_id)

    @with_retry(default=[])
    def _fetch_flights_by_id(self, bounds: str, flight_id: str) -> List[Any]:
        """Internal method with retry logic for fetching flights by ID."""
        return self._api.get_flights(bounds=bounds, flight_id=flight_id)

    def get_flight_details(self, flight_id: str, use_cache: bool = True) -> Optional[FlightDetails]:
        """
        Get detailed information for a specific flight.

        Args:
            flight_id: The flight identifier
            use_cache: Whether to use cached details if available

        Returns:
            FlightDetails object or None if not found
        """
        if use_cache and flight_id in self._details_cache:
            return self._details_cache[flight_id]

        raw_details = self._fetch_flight_details(flight_id)
        if raw_details is None:
            return None

        details = self._parse_flight_details(flight_id, raw_details)
        self._details_cache[flight_id] = details
        return details

    @with_retry(default=None)
    def _fetch_flight_details(self, flight_id: str) -> Optional[Dict]:
        """Internal method with retry logic for fetching flight details."""
        flight_mock = _FlightMock(flight_id)
        return self._api.get_flight_details(flight_mock)

    def get_flight_history(self, flight_id: str) -> List[Dict]:
        """
        Get historical trail data for a flight.

        Args:
            flight_id: The flight identifier

        Returns:
            List of trail points with timestamp, lat, lng, altitude, speed, heading
        """
        details = self.get_flight_details(flight_id)
        if details and details.trail:
            return details.trail
        return []

    def get_flight_playback(self, flight_id: str, timestamp: int) -> Optional[Dict]:
        """
        Get playback data for a historical flight.

        Args:
            flight_id: The flight identifier
            timestamp: Unix timestamp for the flight

        Returns:
            Playback data dict or None
        """
        return self._fetch_flight_playback(flight_id, timestamp)

    @with_retry(default=None)
    def _fetch_flight_playback(self, flight_id: str, timestamp: int) -> Optional[Dict]:
        """Internal method with retry logic for fetching flight playback."""
        flight_mock = _FlightMock(flight_id)
        return self._api.get_flight_playback(flight_mock, timestamp)

    def find_flights(self, callsign: str) -> List[Dict]:
        """
        Search for flights by callsign.

        Args:
            callsign: The flight callsign to search for

        Returns:
            List of matching flight results
        """
        response = self._fetch_find_flights(callsign)
        if response and 'results' in response:
            return response['results']
        return []

    @with_retry(default=None)
    def _fetch_find_flights(self, callsign: str) -> Optional[Dict]:
        """Internal method with retry logic for finding flights."""
        return self._api.find_flights(callsign)

    def clear_cache(self, flight_id: Optional[str] = None):
        """
        Clear cached flight details.

        Args:
            flight_id: Specific flight to clear, or None to clear all
        """
        if flight_id:
            self._details_cache.pop(flight_id, None)
        else:
            self._details_cache.clear()

    @property
    def api(self) -> FlightRadar24API:
        """
        Get the underlying API instance.

        Note: This is provided for backward compatibility during refactoring.
        Prefer using service methods directly when possible.
        """
        return self._api

    def _parse_flight_details(self, flight_id: str, raw: Dict) -> FlightDetails:
        """Parse raw API response into FlightDetails object."""
        details = FlightDetails(id=flight_id, raw_data=raw)

        try:
            details.callsign = raw.get('identification', {}).get('callsign')
        except (KeyError, TypeError):
            pass

        try:
            details.aircraft_model = raw['aircraft']['model']['text']
        except (KeyError, TypeError):
            pass

        try:
            details.airline_name = raw['airline']['name']
        except (KeyError, TypeError):
            pass

        try:
            details.origin_airport = raw['airport']['origin']['name']
        except (KeyError, TypeError):
            pass

        try:
            details.destination_airport = raw['airport']['destination']['name']
        except (KeyError, TypeError):
            pass

        try:
            details.first_timestamp = raw.get('firstTimestamp')
        except (KeyError, TypeError):
            pass

        try:
            details.trail = raw.get('trail', [])
        except (KeyError, TypeError):
            pass

        return details


class _FlightMock:
    """Mock flight object for API compatibility."""

    def __init__(self, flight_id: str):
        self._id = flight_id

    @property
    def id(self) -> str:
        return self._id


# Convenience function for getting the singleton instance
def get_flight_service(api: Optional[FlightRadar24API] = None) -> FlightDataService:
    """
    Get the FlightDataService singleton instance.

    Usage:
        from flight_service import get_flight_service
        service = get_flight_service()
        flights = service.get_flights_in_bounds(bounds)
    """
    return FlightDataService(api)
