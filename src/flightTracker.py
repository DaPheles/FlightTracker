#!/usr/bin/python

from configparser import ConfigParser
from FlightRadar24_patch.api import FlightRadar24API
from sprites import Sprites
from flight import Flight
from tiles import Tiles
from coords import *
from helper import Dict2Class
import tkinter as tk
import time

class FlightTracker(tk.Tk):
  def __init__(self) -> None:
    super().__init__()

    # Main window
    self.title("Flight Tracker")
    self.resizable(False,False)

    # config defaults
    self.home = (52.5162767,13.3777761)
    self.zoom = 11
    self.mapGrid = (4,4)
    self.mapTiles = dict(basemap="terrain", roadmap=False, brightness=0.4)
    self.tileSize = 256       # must remain fixed by now
    self.maxFlightAge = 900   # keep flight history in memory, in seconds
    
    ## config loader, overriding defaults where available
    # Google Maps localization, english per default, can be adjusted through config.ini
    self.localeLang = 'en'
    self.localeCountry = 'GB'
    self.enableRadar = False
    self.enableClouds = False
    self.loadConfig()

    # FlightRadar24 API
    self.fr_api = FlightRadar24API()
    self.fr_api.set_flight_tracker_config(vehicles=0)

    # compute pixel position of home location
    self.homeX, self.homeY = latlngToPixel(self.home, self.zoom)
    # get configuration depending boundaries
    self.bounds = self.getBounds()
    
    # load sprites
    self.sprites = Sprites([25,30,35])  # available sizes: 25,30,35,80
    winIconCfg = Dict2Class(dict(aircraft_code="A380", heading=45))
    self.winIcon = self.sprites.getIcon(winIconCfg, 35, "R")
    self.wm_iconphoto(False, self.winIcon)

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

    # trails
    self.trails = dict()
    self.flights = dict()

    # draw radar
    radarColor = '#222222'
    xc,yc=self.xSize//2,self.ySize//2
    self.C.create_line([xc,0,xc,self.ySize], fill=radarColor)
    self.C.create_line([0,yc,self.xSize,yc], fill=radarColor)
    for i in range(1,min(self.mapGrid)):
      self.C.create_oval([xc-i*self.tileSize//2,yc-i*self.tileSize//2,
                          xc+i*self.tileSize//2,yc+i*self.tileSize//2], outline=radarColor)
    i = min(self.mapGrid)
    self.C.create_oval([xc-i*self.tileSize//2+1,yc-i*self.tileSize//2+1,
                        xc+i*self.tileSize//2-1,yc+i*self.tileSize//2-1], outline=radarColor, width=2)

    # temporal buffer init
    self.tts = dict()
    self.now = time.time()
    self.timestep = 3.2   ;# in seconds
    self.timeout = 900    ;# in seconds
    self.about = dict()

    self.bind('<KeyPress>', self.onKey)
    self.update()
    self.C.after(0,self._update)
    #self.fullscreen = False
    #self.bind('<F12>', self.toggleFullscreen)
    #self.geometrySave = None

  def getBounds(self):
    distX, distY = (self.mapGrid[0]+1.5)/2 * self.tileSize, (self.mapGrid[1]+1.5)/2 * self.tileSize
    boundTL = pixelToLatlng((self.homeX-distX, self.homeY-distY), self.zoom)
    boundBR = pixelToLatlng((self.homeX+distX, self.homeY+distY), self.zoom)
    return f'{boundTL[0]:.6f},{boundBR[0]:.6f},{boundTL[1]:.6f},{boundBR[1]:.6f}'

  def toggleFullscreen(self, event):
    ''' Fullscreen toggle magic, too fuzzy for now to be active '''
    self.fullscreen = not self.fullscreen
    #self.update()
    if self.fullscreen:
        self.geometrySave = self.wm_geometry()
        self.resizable(True,True)
        self.update()
        self.wm_attributes("-fullscreen", True)
        self.xSize = self.winfo_screenwidth()
        self.ySize = self.winfo_screenheight()
        self.C.configure(width=self.xSize, height=self.ySize)
    else:
        self.wm_attributes("-fullscreen", False)
        self.resizable(False,False)
        self.xSize = self.tileSize*self.mapGrid[0]
        self.ySize = self.tileSize*self.mapGrid[1]
        self.C.configure(width=self.xSize, height=self.ySize)
        self.wm_geometry(self.geometrySave)
    self.update()
              
  def loadConfig(self):
    ''' Config loader '''
    config = ConfigParser()
    config.read('config.ini')
    app = 'FlightTracker'

    # get HOME location
    if 'HOME' in config:
      if 'latitude' in config['HOME'] and 'longitude' in config['HOME']:
        lat = float(config['HOME']['latitude'])
        lng = float(config['HOME']['longitude'])
        self.home = (lat,lng)
      else:
        print(f'loadConfig(): HOME config incomplete!')
      if 'zoom' in config['HOME']:
        self.zoom = int(config['HOME']['zoom'])
      if 'timestep' in config['HOME']:
        self.timestep = float(config['HOME']['timestep'])
      if 'localeLang' in config['HOME']:
        self.localeLang = config['HOME']['localeLang']
      if 'localeCountry' in config['HOME']:
        self.localeCountry = config['HOME']['localeCountry']

    if app in config:
      if 'grid' in config[app]:
        values = config[app]['grid'].split(',')
        self.mapGrid = (int(values[0]),int(values[1]))
      if 'basemap' in config[app]:
        self.mapTiles['basemap'] = config[app]['basemap']
      if 'roadmap' in config[app]:
        self.mapTiles['roadmap'] = config.getboolean(app,'roadmap')
      if 'brightness' in config[app]:
        self.mapTiles['brightness'] = config.getfloat(app,'brightness')
      if 'maxFlightAge' in config[app]:
        self.maxFlightAge = config.getint(app,'maxFlightAge')
      if 'enableRainRadar' in config[app]:
        self.enableRadar = config.getboolean(app,'enableRainRadar')
      if 'enableCloudRadar' in config[app]:
        self.enableClouds = config.getboolean(app,'enableCloudRadar')

  def onKey(self, event):
    if event.char == 'c':
      self.tiles.toggleClouds()
      self.tiles.update(self.homeX, self.homeY, self.zoom, force=True)
    elif event.char == 'r':
      self.tiles.toggleRadar()
      self.tiles.update(self.homeX, self.homeY, self.zoom, force=True)
      self.homeRadarIndex = self.tiles.homeRadarIndex

  def getFlightsData(self):
      try:
          return self.fr_api.get_flights(bounds=self.bounds)
      except:
          return list()

  def _update(self):

    # update tiles
    now = int(time.time())
    tilets_ = now-(now%300)  # 5 min granularity for radar update period
    if self.tileTs != tilets_:
      # Tiles reload
      self.tiles.update(self.homeX, self.homeY, self.zoom, force=True)
      self.homeRadarIndex = self.tiles.homeRadarIndex
      self.tileTs = tilets_

      #now_str = time.strftime("%Y-%m-%d-%H:%M", time.gmtime(tilets_))
      #print(f"{now_str}: Number of tracked flights: {len(self.flights)}")
      #smpls = 0
      #for flid in self.flights:
      #  smpls += len(self.flights[flid].past_loc)
      #print(f"{now_str}: Number of maintained samples: {smpls}")

    # get local flights in sight
    flights = self.getFlightsData()

    # cycle through all flights
    flight_ids = list()
    for fl in flights:
      id = fl.id
      if id not in self.flights:
        # create flight object
        self.flights[id] = Flight(self.tk, self.fr_api, self.C, maxFlightAge=self.maxFlightAge, centerview=True)
        # define drawing offset
        self.flights[id].init_offsets(self.xSize//2 - self.homeX, self.ySize//2 - self.homeY)
        self.flights[id].init_sprites(self.sprites)
        self.flights[id].init_zoom(self.zoom)

      # update object with new details
      self.flights[id].update(fl, now)

      # check maximum processing period
      delta = int((self.timestep-(time.time()-self.now))*1000)
      if delta < 50:
        # loop takes too long, breaking up here for now
        break

      flight_ids.append(id)
      #self.trails[id].update()
    # END cycle through all flights

    # lift all plane icons, update old flights
    for id in list(self.flights.keys()):
      if now - self.flights[id].last_seen() > self.maxFlightAge:
        # delete flight if no new data arrived for more than 5 minutes
        # reason: either out of range or landed
        self.flights[id].cleanup()
        del self.flights[id]
      else:
        if id not in flight_ids:
          # update all trails that were not recently updated
          self.flights[id].ping(now)
        else:
          # lift all plane and detail objects
          self.flights[id].lift_plane()

    # update every 2 second
    delta = int((self.timestep-(time.time()-self.now))*1000)
    if delta < 10:
      # use current timestamp if processing latency is larger than timestep
      self.now = time.time()
      delta = 10
    else:
      # use timestep as increment to precicely synchronize to the continuous timeline
      self.now += self.timestep

    title = f"Flight Tracker - Tracked flights:{len(self.flights)}"
    if self.tiles.enableRadar:
       title += f" - Rain Index:{self.homeRadarIndex}"
    self.title(title)

    self.update()
    self.C.after(delta,self._update)

if __name__ == "__main__":
  # create Application
  ft = FlightTracker()
  ft.mainloop()
