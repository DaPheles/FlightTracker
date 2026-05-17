#!/usr/bin/python

from sprites import Sprites
from flight import Flight, FlightFactory
from tiles import Tiles
from coords import *
from helper import Dict2Class
from logger import get_logger
from config_manager import get_config
from flight_service import get_flight_service
import tkinter as tk
import time
import threading

logger = get_logger(__name__)

class FlightTracker(tk.Tk):
  def __init__(self) -> None:
    super().__init__()

    # Main window
    self.title("Flight Tracker")
    self.resizable(False,False)

    # Load configuration
    config = get_config()
    home_cfg = config.home
    app_cfg = config.flight_tracker

    # Apply configuration
    self.home = home_cfg.location
    self.zoom = home_cfg.zoom
    self.timestep = home_cfg.timestep
    self.localeLang = home_cfg.locale_lang
    self.localeCountry = home_cfg.locale_country

    self.mapGrid = app_cfg.grid
    self.mapTiles = dict(
        basemap=app_cfg.map_tiles.basemap,
        roadmap=app_cfg.map_tiles.roadmap,
        brightness=app_cfg.map_tiles.brightness
    )
    self.tileSize = 256  # fixed tile size
    self.maxFlightAge = app_cfg.max_flight_age
    self.enableRadar = app_cfg.enable_rain_radar
    self.enableClouds = app_cfg.enable_cloud_radar
    self.enableEkf = app_cfg.enable_ekf
    self.animationRate = app_cfg.animation_rate
    self._anim_interval_ms = max(50, int(1000.0 / self.animationRate))

    # Flight data service (handles API access)
    self._flight_service = get_flight_service()

    # compute pixel position of home location
    _p = latlngToPixel(self.home, self.zoom)
    self.homeX, self.homeY = _p.x, _p.y
    # get configuration depending boundaries
    self.bounds = self.getBounds()
    
    # load sprites
    self.sprites = Sprites()
    winIconCfg = Dict2Class(dict(aircraft_code="A380", heading=45))
    self.winIcon = self.sprites.getIcon(winIconCfg, 80, 6.0)
    self.wm_iconphoto(False, self.winIcon)
    self.iconphoto(False, self.winIcon)

    # map stuff
    self.xSize = self.tileSize*self.mapGrid[0]
    self.ySize = self.tileSize*self.mapGrid[1]
    self.C = tk.Canvas(self, width=self.xSize, height=self.ySize)
    self.C.pack()
    self.tiles = Tiles(self.C, self.tileSize, self.mapGrid, self.mapTiles, self.zoom, self.home)   # tileSize is 256!
    self.tiles.enableRadar = self.enableRadar
    self.tiles.enableClouds = self.enableClouds
    self.tiles.setLocale(self.localeLang, self.localeCountry)
    self.tiles.update(self.homeX, self.homeY, self.zoom, force=True)
    tilets_ = int(time.time())
    self.tileTs = tilets_-(tilets_%300)  # 5 min granularity for radar update period
    self.homeRadarIndex = self.tiles.homeRadarIndex

    # trails and flights
    self.trails = dict()
    self.flights = dict()

    # Flight factory for creating flight objects
    self._flight_factory = FlightFactory(self.tk, self._flight_service.api, self.C, self.sprites,
                                          enable_ekf=self.enableEkf)
    self._flight_offsets = (self.xSize//2 - self.homeX, self.ySize//2 - self.homeY)

    # draw radar
    self._draw_radar()

    # temporal buffer init
    self.tts = dict()
    self.now = time.time()
    self.timestep = 3.2   ;# in seconds
    self.timeout = 900    ;# in seconds
    self.about = dict()

    # async fetch state
    self._fetching = False
    self._pending_flights = None

    self.bind('<KeyPress>', self.onKey)
    self.update()
    self._start_fetch()   # kick off first fetch eagerly to reduce startup latency
    self.C.after(0, self._update)
    if self.enableEkf:
      self.C.after(self._anim_interval_ms, self._anim_loop)
    self.fullscreen = False
    self.bind('<F12>', self.toggleFullscreen)
    #self.geometrySave = None

  def getBounds(self):
    distX, distY = (self.mapGrid[0]+1.5)/2 * self.tileSize, (self.mapGrid[1]+1.5)/2 * self.tileSize
    boundTL = pixelToLatlng(PixelCoord(self.homeX-distX, self.homeY-distY), self.zoom)
    boundBR = pixelToLatlng(PixelCoord(self.homeX+distX, self.homeY+distY), self.zoom)
    return f'{boundTL.lat:.6f},{boundBR.lat:.6f},{boundTL.lng:.6f},{boundBR.lng:.6f}'

  def _draw_radar(self):
    """Draw radar crosshairs and distance circles; clears previous items first."""
    self.C.delete('radar')
    radarColor = '#222222'
    xc, yc = self.xSize // 2, self.ySize // 2
    self.C.create_line([xc, 0, xc, self.ySize], fill=radarColor, tags='radar')
    self.C.create_line([0, yc, self.xSize, yc], fill=radarColor, tags='radar')
    for i in range(1, min(self.mapGrid)):
      self.C.create_oval([xc-i*self.tileSize//2, yc-i*self.tileSize//2,
                          xc+i*self.tileSize//2, yc+i*self.tileSize//2],
                         outline=radarColor, tags='radar')
    i = min(self.mapGrid)
    self.C.create_oval([xc-i*self.tileSize//2+1, yc-i*self.tileSize//2+1,
                        xc+i*self.tileSize//2-1, yc+i*self.tileSize//2-1],
                       outline=radarColor, width=2, tags='radar')

  def toggleFullscreen(self, event):
    """Toggle fullscreen mode; recalculates grid, bounds, offsets and reloads tiles."""
    old_xSize = self.xSize
    old_ySize = self.ySize
    self.fullscreen = not self.fullscreen

    if self.fullscreen:
        self.geometrySave = self.wm_geometry()
        self._mapGrid_normal = self.mapGrid
        self.resizable(True, True)
        self.update()
        self.wm_attributes("-fullscreen", True)
        self.xSize = self.winfo_screenwidth()
        self.ySize = self.winfo_screenheight()
        self.mapGrid = (self.xSize // self.tileSize, self.ySize // self.tileSize)
    else:
        self.wm_attributes("-fullscreen", False)
        self.resizable(False, False)
        self.mapGrid = self._mapGrid_normal
        self.xSize = self.tileSize * self.mapGrid[0]
        self.ySize = self.tileSize * self.mapGrid[1]
        self.wm_geometry(self.geometrySave)

    self.C.configure(width=self.xSize, height=self.ySize)

    # Update tile grid for new canvas dimensions
    self.tiles.tileNum_ = self.mapGrid

    # Recalculate flight bounds for new grid coverage
    self.bounds = self.getBounds()

    # Shift all existing flight canvas items and anchors to new canvas center
    dx = self.xSize // 2 - old_xSize // 2
    dy = self.ySize // 2 - old_ySize // 2
    for flight in self.flights.values():
        flight.reposition(dx, dy, self.xSize, self.ySize)
    self._flight_offsets = (self.xSize // 2 - self.homeX, self.ySize // 2 - self.homeY)

    # Move the home-location focus dot to the new canvas centre
    if self.tiles.focus_ is not None:
        cx, cy = self.xSize // 2, self.ySize // 2
        self.C.coords(self.tiles.focus_, cx-5, cy-5, cx+5, cy+5)

    # Redraw radar decorations at new dimensions
    self._draw_radar()

    # Reload tiles to fill the new canvas
    self.tiles.update(self.homeX, self.homeY, self.zoom, force=True)

    self.update()
    logger.debug(f"Window size: {self.xSize}x{self.ySize}, grid: {self.mapGrid}")
              
  def onKey(self, event):
    if event.char == 'c':
      self.tiles.toggleClouds()
      self.tiles.update(self.homeX, self.homeY, self.zoom, force=True)
    elif event.char == 'r':
      self.tiles.toggleRadar()
      self.tiles.update(self.homeX, self.homeY, self.zoom, force=True)
      self.homeRadarIndex = self.tiles.homeRadarIndex

  def getFlightsData(self):
      """Get flights within the configured bounds using the flight service."""
      return self._flight_service.get_flights_in_bounds(self.bounds)

  def _start_fetch(self):
      """Start a background fetch if one is not already running."""
      if self._fetching:
          return
      self._fetching = True
      threading.Thread(target=self._fetch_bg, daemon=True).start()

  def _fetch_bg(self):
      """Fetch flight data in background thread; result stored in _pending_flights."""
      try:
          flights = self.getFlightsData()
      except Exception:
          flights = []
      self._pending_flights = flights
      self._fetching = False

  def _anim_loop(self):
    """High-frequency animation — moves canvas items only, no API calls."""
    now = time.monotonic()
    for flight in self.flights.values():
      flight.animate(now)
    self.C.after(self._anim_interval_ms, self._anim_loop)

  def _update(self):

    # start background fetch (non-blocking if already running)
    self._start_fetch()

    # update tiles
    now = int(time.time())
    tilets_ = now-(now%300)  # 5 min granularity for radar update period
    if self.tileTs != tilets_:
      # Tiles reload
      self.tiles.update(self.homeX, self.homeY, self.zoom, force=True)
      self.homeRadarIndex = self.tiles.homeRadarIndex
      self.tileTs = tilets_

    # consume pending flight data produced by background thread
    flight_ids = list()
    if self._pending_flights is not None:
      flights = self._pending_flights
      self._pending_flights = None

      # cycle through all flights
      for fl in flights:
        id = fl.id
        if id not in self.flights:
          # create flight object using factory
          self.flights[id] = self._flight_factory.create(
              offsets=self._flight_offsets,
              zoom=self.zoom,
              max_flight_age=self.maxFlightAge
          )

        # update object with new details
        self.flights[id].update(fl, now)

        # check maximum processing period
        delta = int((self.timestep-(time.time()-self.now))*1000)
        if delta < 50:
          # loop takes too long, breaking up here for now
          break

        flight_ids.append(id)
      # END cycle through all flights

    # lift all plane icons, update old flights
    for id in list(self.flights.keys()):
      if now - self.flights[id].last_seen() > self.maxFlightAge:
        # delete flight if no new data arrived for more than 5 minutes
        # reason: either out of range or landed
        self.flights[id].destroy()
        del self.flights[id]
      else:
        if id not in flight_ids:
          # update all trails that were not recently updated
          self.flights[id].ping(now)
        else:
          # lift all plane and detail objects
          self.flights[id].lift_plane()

    # update window title
    title = f"Flight Tracker - Tracked flights:{len(self.flights)}"
    if self.tiles.enableRadar:
       title += f" - Rain Index:{self.homeRadarIndex}"
    if self.tiles.enableClouds:
       title += " - C"
    self.title(title)

    # periodic updates, find remaining delta to configured timestep
    delta_ms = int((self.timestep-(time.time()-self.now))*1000)
    if delta_ms < 10:
      # use current timestamp if processing latency is larger than timestep
      self.now = time.time()
      delta_ms = 10
    else:
      # use timestep as increment to precicely synchronize to the continuous timeline
      self.now += self.timestep

    self.update()
    self.C.after(delta_ms, self._update)

if __name__ == "__main__":
  # create Application
  ft = FlightTracker()
  ft.mainloop()
