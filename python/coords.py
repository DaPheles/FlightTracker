'''
    Helper module for world coordinate calculations.
    Handles conversions between lat/lng, world coordinates, and pixel coordinates.
'''

import math
from dataclasses import dataclass


@dataclass
class LatLng:
    """Latitude/longitude coordinate pair in degrees."""
    lat: float
    lng: float


@dataclass
class PixelCoord:
    """Pixel coordinate pair (x, y) at a given zoom level."""
    x: float
    y: float


@dataclass
class WorldCoord:
    """Google Maps world coordinate pair (x, y)."""
    x: float
    y: float


def lngToXWorld(lng: float) -> float:
    """
    Convert longitude to Google Maps world coordinate X value.

    Args:
        lng: Longitude value in degrees

    Returns:
        X value of the corresponding Google Maps world coordinate
    """
    circumference = 256.0
    radius = circumference / (2 * math.pi)
    falseEasting = -1.0 * circumference / 2.0
    return (radius * math.radians(lng)) - falseEasting


def latToYWorld(lat: float) -> float:
    """
    Convert latitude to Google Maps world coordinate Y value.

    Args:
        lat: Latitude value in degrees

    Returns:
        Y value of the corresponding Google Maps world coordinate
    """
    circumference = 256.0
    radius = circumference / (2 * math.pi)
    falseNorthing = circumference / 2.0
    sinradLat = math.sin(math.radians(lat))
    return ((radius / 2.0 * math.log((1.0 + sinradLat) / (1.0 - sinradLat)))
            - falseNorthing) * -1


def worldToPixel(xWorld: float, yWorld: float, zoomLevel: int) -> PixelCoord:
    """
    Convert world coordinates to pixel coordinates at given zoom level.

    Args:
        xWorld: X value of the world coordinate
        yWorld: Y value of the world coordinate
        zoomLevel: Map zoom level (0-21)

    Returns:
        Pixel with x and y pixel coordinates
    """
    zoom = math.pow(2, zoomLevel)
    x = round(xWorld * zoom)
    y = round(yWorld * zoom)
    return PixelCoord(x, y)


def latlngToPixel(latlng: LatLng, zoom: int) -> PixelCoord:
    """
    Convert lat/lng coordinates to pixel coordinates at given zoom level.

    Args:
        latlng: LatLng with lat and lng in degrees
        zoom: Map zoom level (0-21)

    Returns:
        Pixel with x and y pixel coordinates
    """
    return worldToPixel(lngToXWorld(latlng.lng), latToYWorld(latlng.lat), zoom)

# ---- Inverse functions ---- #

def xWorldToLng(xWorld: float) -> float:
    """
    Convert Google Maps world coordinate X value to longitude.

    Args:
        xWorld: X value of the world coordinate

    Returns:
        Longitude value in degrees
    """
    circumference = 256.0
    radius = circumference / (2 * math.pi)
    falseEasting = -1.0 * circumference / 2.0
    return math.degrees((xWorld + falseEasting) / radius)


def yWorldToLat(yWorld: float) -> float:
    """
    Convert Google Maps world coordinate Y value to latitude.

    Args:
        yWorld: Y value of the world coordinate

    Returns:
        Latitude value in degrees
    """
    circumference = 256.0
    radius = circumference / (2 * math.pi)
    falseNorthing = circumference / 2.0
    t_ = math.exp(((yWorld * -1) + falseNorthing) * 2 / radius)
    return math.degrees(math.asin(-1 * (1 - t_) / (1 + t_)))


def pixelToWorld(pixel: PixelCoord, zoomLevel: int) -> WorldCoord:
    """
    Convert pixel coordinates to world coordinates at given zoom level.

    Args:
        pixel: Pixel with x and y coordinates
        zoomLevel: Map zoom level (0-21)

    Returns:
        WorldCoord with x and y world coordinates
    """
    zoom = math.pow(2, zoomLevel)
    xWorld = pixel.x / zoom
    yWorld = pixel.y / zoom
    return WorldCoord(xWorld, yWorld)


def pixelToLatlng(pixel: PixelCoord, zoom: int) -> LatLng:
    """
    Convert pixel coordinates to lat/lng at given zoom level.

    Args:
        pixel: Pixel with x and y coordinates
        zoom: Map zoom level (0-21)

    Returns:
        LatLng with lat and lng in degrees
    """
    t_ = pixelToWorld(pixel, zoom)
    return LatLng(yWorldToLat(t_.y), xWorldToLng(t_.x))


# ---- Distance and bearing calculations ---- #

def haversine(latlng1: LatLng, latlng2: LatLng) -> float:
    """
    Calculate the great-circle distance between two points using the Haversine formula.

    Args:
        latlng1: First point as LatLng in degrees
        latlng2: Second point as LatLng in degrees

    Returns:
        Distance in kilometers
    """
    R = 6372.8  # Earth radius in kilometers

    dLat = math.radians(latlng2.lat - latlng1.lat)
    dLon = math.radians(latlng2.lng - latlng1.lng)
    lat1 = math.radians(latlng1.lat)
    lat2 = math.radians(latlng2.lat)

    a = math.sin(dLat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dLon / 2)**2
    c = 2 * math.asin(math.sqrt(a))

    return R * c


def get_bearing(latlng1: LatLng, latlng2: LatLng) -> float:
    """
    Calculate the initial bearing from point A to point B.

    Args:
        latlng1: Starting point as LatLng in degrees
        latlng2: Ending point as LatLng in degrees

    Returns:
        Bearing in degrees (0-360, where 0 is north)
    """
    dLng = math.radians(latlng2.lng - latlng1.lng)
    x = math.cos(math.radians(latlng2.lat)) * math.sin(dLng)
    y = (math.cos(math.radians(latlng1.lat)) * math.sin(math.radians(latlng2.lat)) -
         math.sin(math.radians(latlng1.lat)) * math.cos(math.radians(latlng2.lat)) * math.cos(dLng))
    theta = math.atan2(x, y)
    if theta < 0.0:
        theta += math.pi * 2
    return math.degrees(theta)
