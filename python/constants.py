'''
    Constants and configuration values for the Flight Tracker application.
    Centralizes magic numbers and default values for easier maintenance.
'''

# ============================================================================
# Map and Tile Constants
# ============================================================================

TILE_SIZE = 256  # Google Maps tile size in pixels (fixed)
DEFAULT_ZOOM = 11  # Default map zoom level
MIN_ZOOM = 0
MAX_ZOOM = 21

# Map styles
MAP_STYLE_TERRAIN = 'terrain'
MAP_STYLE_SATELLITE = 'satellite'
MAP_STYLE_ROADMAP = 'roadmap'

# Default map brightness (0.0 - 1.0)
DEFAULT_BRIGHTNESS = 0.4

# Cloud overlay alpha (0.0 - 1.0)
CLOUDS_ALPHA = 0.6

# ============================================================================
# Timing Constants (in seconds)
# ============================================================================

# API update intervals
DEFAULT_TIMESTEP = 3.2  # Default update interval for flight data
ISS_TIMESTEP = 0.25  # ISS position update interval (faster due to speed)
FOLLOW_FLIGHT_TIMESTEP = 2.0  # Follow flight update interval
OFFLINE_CHECK_INTERVAL = 15.0  # Interval when flight goes offline

# Radar/weather update granularity (5 minutes)
RADAR_UPDATE_GRANULARITY = 300  # 5 * 60 seconds

# Flight age limits
DEFAULT_MAX_FLIGHT_AGE = 1200  # 20 minutes - keep flight in memory
FLIGHT_TIMEOUT = 900  # 15 minutes - consider flight offline

# Lost flight threshold
MAX_LOST_COUNT = 10  # Number of failed updates before giving up

# ============================================================================
# Trail Constants
# ============================================================================

DEFAULT_MAX_TRAIL_POINTS = 150  # Maximum number of trail points to keep
TRAIL_UPDATE_INTERVAL = 30  # Seconds between trail history updates
ISS_TRAIL_UPDATE_INTERVAL = 2  # Faster updates for ISS

# Trail time gap filtering (seconds)
TRAIL_MIN_TIME_GAP = 5  # Minimum time between trail points

# ============================================================================
# UI Constants
# ============================================================================

# Default grid sizes (tiles x tiles)
DEFAULT_FLIGHT_TRACKER_GRID = (5, 5)
DEFAULT_FOLLOW_FLIGHT_GRID = (4, 4)

# Icon sizes
PLANE_ICON_SIZE = 80
PLANE_ICON_ALTITUDE_SCALE = 7.25  # Altitude scaling factor for icon size

# Tooltip offsets
TOOLTIP_DELAY_MS = 0  # Delay before showing tooltip
TOOLTIP_OFFSET = (4, 12)  # (x, y) offset from cursor

# Radar overlay colors
RADAR_OVERLAY_COLOR = '#222222'

# ============================================================================
# Geographic Constants
# ============================================================================

EARTH_RADIUS_KM = 6372.8  # Earth radius in kilometers (for haversine)

# Default home location (Berlin, Germany)
DEFAULT_LATITUDE = 52.5162767
DEFAULT_LONGITUDE = 13.3777761

# ============================================================================
# API Constants
# ============================================================================

# Request timeouts (milliseconds)
API_TIMEOUT_MS = 10000  # 10 seconds
TILE_DOWNLOAD_TIMEOUT_MS = 30000  # 30 seconds

# Retry settings
MAX_API_RETRIES = 3
RETRY_DELAY_MS = 1000  # 1 second between retries

# Cache settings
FLIGHT_DETAILS_CACHE_TTL = 300  # 5 minutes cache for flight details

# ============================================================================
# Unit Conversion Constants
# ============================================================================

FEET_TO_KM = 0.0003048  # 1 foot = 0.0003048 km
KNOTS_TO_KMH = 1.852  # 1 knot = 1.852 km/h
METERS_TO_FEET = 3.28084  # 1 meter = 3.28084 feet

# ============================================================================
# Altitude Thresholds (in feet)
# ============================================================================

ALTITUDE_GROUND = 0
ALTITUDE_LOW = 5000  # Below this is low altitude
ALTITUDE_MEDIUM = 20000  # Below this is medium altitude
ALTITUDE_HIGH = 35000  # Above this is high altitude (cruising)
ALTITUDE_ISS = 408000  # ISS orbital altitude (~408 km)

# ============================================================================
# Color Constants (HSV values for altitude coloring)
# ============================================================================

# Trail colors based on altitude (hue values 0-360)
TRAIL_HUE_LOW = 0  # Red for low altitude
TRAIL_HUE_MEDIUM = 60  # Yellow for medium altitude
TRAIL_HUE_HIGH = 120  # Green for high altitude
TRAIL_HUE_CRUISING = 240  # Blue for cruising altitude
