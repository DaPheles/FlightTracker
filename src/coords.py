'''
    helper script for world coordinate calculations
'''

import math

def lngToXWorld(lng):
    """
    * Converts the given longitude value to the x value of the Google Maps world coordinate.
    * 
    * @param lng the longitude value
    * @return the x value of the corresponding Google Maps world coordinate
    """
    tiles = math.pow(2, 0)
    circumference = 256 * tiles
    radius = circumference / (2 * math.pi)
    falseEasting = -1.0 * circumference / 2.0
    return (radius * math.radians(lng)) - falseEasting

def latToYWorld(lat):
    """
    * Converts the given latitude value to the y value of the Google Maps world coordinate.
    * 
    * @param lat the latitude value
    * @return the y value of the corresponding Google Maps world coordinate
    """
    tiles = math.pow(2, 0)
    circumference = 256 * tiles
    radius = circumference / (2 * math.pi)
    falseNorthing = circumference / 2.0
    #return ((radius / 2.0 * math.log((1.0 + math.sin(math.radians(lat)))\
    #        / (1.0 - math.sin(math.radians(lat))))) - falseNorthing)\
    #        * -1
    sinradLat = math.sin(math.radians(lat))
    return ((radius / 2.0 * math.log((1.0 + sinradLat) / (1.0 - sinradLat))) \
            - falseNorthing) * -1

def worldToPixel(xWorld, yWorld, zoomLevel):
    """
    * Converts the given world coordinates to the pixel coordinates corresponding to the given zoom level.
    * 
    * @param xWorld the x value of the world coordinate
    * @param yWorld the y value of the world coordinate
    * @param zoomLevel the zoom level
    * @return the pixel coordinates as a Point (x,y)
    """
    zoom = math.pow(2, zoomLevel)
    x = round(xWorld * zoom)
    y = round(yWorld * zoom)
    return (x, y)

def latlngToPixel(latlng, zoom):
    """
    * Converts the given latlong coordinates to the pixel coordinates corresponding to the given zoom level.
    * 
    * @param latlng the value of the latlong coordinate (tuple of (lat,lng))
    * @param zoom the zoom level
    * @return the pixel coordinates as a Point (x,y)
    """
    return worldToPixel(lngToXWorld(latlng[1]), latToYWorld(latlng[0]), zoom)

#---- inverse functions ----#

def xWorldToLng(xWorld):
    """
    * Converts the given x value of the Google Maps world coordinate to the longitude value.
    * 
    * @param xWorld the x value of the world coordinate
    * @return the longitude value
    """
    tiles = math.pow(2, 0)
    circumference = 256 * tiles
    radius = circumference / (2 * math.pi)
    falseEasting = -1.0 * circumference / 2.0
    #return (radius * math.radians(lng)) - falseEasting
    return math.degrees((xWorld + falseEasting) / radius)

def yWorldToLat(yWorld):
    """
    * Converts the given y value of the Google Maps world coordinate to the latitude value.
    * 
    * @param yWorld the y value of the corresponding Google Maps world coordinate
    * @return the latitude value
    """
    tiles = math.pow(2, 0)
    circumference = 256 * tiles
    radius = circumference / (2 * math.pi)
    falseNorthing = circumference / 2.0
    #sinradLat = math.sin(math.radians(lat))
    #return ((radius / 2.0 * math.log((1.0 + sinradLat) / (1.0 - sinradLat))) \
    #        - falseNorthing) * -1
    t_ = math.exp(((yWorld * -1) + falseNorthing) * 2 / radius)
    return math.degrees(math.asin(-1 * (1 - t_) / (1 + t_)))

def pixelToWorld(x, y, zoomLevel):
    """
    * Converts the given pixel coordinates corresponding to the given zoom level to the world coordinates.
    * 
    * @param x the x value of the pixel coordinate
    * @param y the y value of the pixel coordinate
    * @param zoomLevel the zoom level
    * @return the world coordinates as a Point (xWorld,yWorld)
    """
    zoom = math.pow(2, zoomLevel)
    xWorld = x / zoom
    yWorld = y / zoom
    return xWorld, yWorld

def pixelToLatlng(pixel, zoom):
    """
    * Converts the given pixel coordinate corresponding a given zoom level to the latlong coordinates.
    * 
    * @param pixel the pixel coordinates as a Point (x,y)
    * @param zoom the zoom level
    * @return the latlong coordinate (tuple of (lat,lng)
    """
    #return worldToPixel(lngToXWorld(latlng[1]), latToYWorld(latlng[0]), zoom)
    t_ = pixelToWorld(*pixel, zoom)
    return yWorldToLat(t_[1]), xWorldToLng(t_[0])

#---- misc ----#

def haversine(latlng1, latlng2):
    """
    * Haversine algorithm to compute the distance between two locations
    *
    * @param latlng1 the first latlong coordinate (tuple of (lat,lng)
    * @param latlng2 the first latlong coordinate (tuple of (lat,lng)
    * @return the distance in km
    """
    R = 6372.8  # Earth radius in kilometers
    
    dLat = math.radians(latlng2[0] - latlng1[0])
    dLon = math.radians(latlng2[1] - latlng1[1])
    lat1 = math.radians(latlng1[0])
    lat2 = math.radians(latlng2[0])
    
    a = math.sin(dLat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dLon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c
