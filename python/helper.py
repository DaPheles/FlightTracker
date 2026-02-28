'''
    Helper utilities and conversion functions for Flight Tracker.
'''

from typing import Dict, Any, Tuple
from constants import FEET_TO_KM, KNOTS_TO_KMH


class Dict2Class:
    """
    Convert a dictionary to an object with attribute access.

    Useful for mocking API response objects.

    Usage:
        data = {'name': 'Flight123', 'altitude': 35000}
        obj = Dict2Class(data)
        print(obj.name)  # 'Flight123'
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        """
        Initialize with dictionary data.

        Args:
            data: Dictionary to convert to object attributes
        """
        for key, value in data.items():
            setattr(self, key, value)

    def __repr__(self) -> str:
        attrs = ', '.join(f'{k}={v!r}' for k, v in self.__dict__.items())
        return f'Dict2Class({attrs})'


def ft2km(feet: float) -> float:
    """
    Convert feet to kilometers.

    Args:
        feet: Altitude/distance in feet

    Returns:
        Equivalent value in kilometers
    """
    return feet * FEET_TO_KM


def ft2m(feet: float) -> float:
    """
    Convert feet to meters.

    Args:
        feet: Altitude/distance in feet

    Returns:
        Equivalent value in meters
    """
    return feet * FEET_TO_KM * 1000


def kts2kmh(knots: float) -> float:
    """
    Convert knots to kilometers per hour.

    Args:
        knots: Speed in knots

    Returns:
        Equivalent speed in km/h
    """
    return knots * KNOTS_TO_KMH


def kmh2kts(kmh: float) -> float:
    """
    Convert kilometers per hour to knots.

    Args:
        kmh: Speed in km/h

    Returns:
        Equivalent speed in knots
    """
    return kmh / KNOTS_TO_KMH


def hsv2rgb(hsv: Tuple[float, float, float]) -> str:
    """
    Convert HSV color to RGB hex string.

    Args:
        hsv: Tuple of (hue, saturation, value) where:
             - hue: 0.0-1.0 (0=red, 0.33=green, 0.67=blue)
             - saturation: 0.0-1.0
             - value: 0.0-1.0

    Returns:
        RGB hex color string (e.g., '#FF0000' for red)
    """
    h, s, v = hsv

    h8 = h * 8
    hi = int(h8)
    f = h8 - hi

    vs = v * s
    vsf = vs * f
    p = v - vs
    q = v - vsf
    t = v - vs + vsf

    if hi == 0:
        r, g, b = v, t, p
    elif hi == 1:
        r, g, b = q, v, p
    elif hi == 2:
        r, g, b = p, v, t
    elif hi == 3:
        r, g, b = p, q, v
    elif hi == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q

    return f"#{int(255*r):02X}{int(255*g):02X}{int(255*b):02X}"


#def rgb2hsv(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
#    """
#    Convert RGB color to HSV.
#
#    Args:
#        rgb: Tuple of (red, green, blue) where each is 0-255
#
#    Returns:
#        Tuple of (hue, saturation, value) where each is 0.0-1.0
#    """
#    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
#    max_c = max(r, g, b)
#    min_c = min(r, g, b)
#    diff = max_c - min_c
#
#    # Value
#    v = max_c
#
#    # Saturation
#    s = 0.0 if max_c == 0 else diff / max_c
#
#    # Hue
#    if diff == 0:
#        h = 0.0
#    elif max_c == r:
#        h = (g - b) / diff % 6
#    elif max_c == g:
#        h = (b - r) / diff + 2
#    else:
#        h = (r - g) / diff + 4
#    h /= 6
#
#    return (h, s, v)

