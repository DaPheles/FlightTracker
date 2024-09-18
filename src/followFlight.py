'''
    Application to follow flights using FlightRadar24 API and Google Maps tiles
'''

from FlightRadar24_patch.api import FlightRadar24API
from configparser import ConfigParser
from hover import CanvasToolTip
from sprites import Sprites
from tiles import Tiles
from trails import Trails
from coords import *
from helper import Dict2Class
import tkinter as tk
import time, json

class FollowFlight:
  def __init__(self, tk_root, flight, fr_api=None, saveHistory=False, destroyEvent=None) -> None:
    self.tk = tk_root
    self.top = tk.Toplevel()
    self.top.title("Follow Flight")
    self.top.resizable(False,False)
    if destroyEvent is not None:
      self.top.protocol("WM_DELETE_WINDOW", destroyEvent)

    # config defaults
    self.home = (52.5162767,13.3777761)
    self.zoom = 10
    self.mapGrid = (4,4)
    self.mapTiles = dict(basemap="terrain", roadmap=False, brightness=0.4)
    self.tileSize = 256   # must remain fixed by now
    self.centerview = True
    self.maxtrail = 100

    # config loader, overriding defaults where available
    self.localeLang = 'en'
    self.localeCountry = 'EN'
    self.enableRadar = False
    self.enableClouds = False
    self.loadConfig()

    self.f = None
    self.flight = flight
    self.fr_api = fr_api if fr_api else FlightRadar24API()
    self.saveHistory = saveHistory

    self.online = False
    self.now = time.time()
    self.timestep = 3.2   ;# in seconds
    self.timestep_lost = 15.0   ;# in seconds
    self.past_loc = self.home
    self.past_details = None
    self.lost_count = 0
    
    # load sprites
    self.sprites = Sprites([80])
    self.iconImage = None
    self.icon = None

    # map stuff
    self.latitude = -1
    self.longitude = -1
    self.zoom = 12
    self.C = tk.Canvas(self.top,
                       width=self.tileSize*self.mapGrid[0], 
                       height=self.tileSize*self.mapGrid[1])
    self.C.pack()

    self.tiles = Tiles(self.C, self.tileSize, self.mapGrid, self.mapTiles, self.zoom, self.home, self.centerview)   # tileSize is 256!
    self.tiles.enableRadar = self.enableRadar
    self.tiles.enableClouds = self.enableClouds
    self.tiles.setLocale(self.localeLang, self.localeCountry)
    homeX, homeY = latlngToPixel(self.home, self.zoom)
    self.tiles.update(homeX, homeY, self.zoom, force=True)

    # trails
    self.trails = Trails(self.fr_api, flight, self.tiles, self.maxtrail, self.centerview)

    # prepare initial trail trace
    self.trailPoly = self.C.create_line([0,0,0,0], fill="#AA8866", width=5, smooth=1)
    self.tts = CanvasToolTip(self.C, self.trailPoly, "")

    # start periodic update cycles
    self.top.bind('<KeyPress>', self.onKey)
    self.C.after(0,self._update)

  def loadConfig(self):
    ''' Config loader '''
    config = ConfigParser()
    config.read('config.ini')
    app = 'FollowFlight'

    # get HOME location
    if 'HOME' in config:
      if 'latitude' in config['HOME'] and 'longitude' in config['HOME']:
        lat = config.getfloat('HOME','latitude')
        lng = config.getfloat('HOME','longitude')
        self.home = (lat,lng)
      else:
        print(f'loadConfig(): HOME config incomplete!')
      if 'zoom' in config['HOME']:
        self.zoom = config.getint('HOME','zoom')
      if 'localeLang' in config['HOME']:
        self.localeLang = config['HOME']['localeLang']
      if 'localeCountry' in config['HOME']:
        self.localeCountry = config['HOME']['localeCountry']

    if app in config:
      if 'grid' in config[app]:
        values = config.get(app,'grid').split(',')
        self.mapGrid = (int(values[0]),int(values[1]))
      if 'basemap' in config[app]:
        self.mapTiles['basemap'] = config.get(app,'basemap')
      if 'roadmap' in config[app]:
        self.mapTiles['roadmap'] = config.getboolean(app,'roadmap')
      if 'brightness' in config[app]:
        self.mapTiles['brightness'] = config.getfloat(app,'brightness')
      if 'centerview' in config[app]:
        self.centerview = config.getboolean(app,'centerview')
      if 'maxtrail' in config[app]:
        self.maxtrail = config.getint(app,'maxtrail')
      if 'enableRainRadar' in config[app]:
        self.enableRadar = config.getboolean(app,'enableRainRadar')
      if 'enableCloudRadar' in config[app]:
        self.enableClouds = config.getboolean(app,'enableCloudRadar')
    else:
      print(f'{app} not found!')

  def onKey(self, event):
    if event.char == "c":
      self.tiles.toggleClouds()
      self.tiles.update(self.latitude, self.longitude, self.zoom, force=True)
    elif event.char == "r":
      self.tiles.toggleRadar()
      self.tiles.update(self.latitude, self.longitude, self.zoom, force=True)

  def getFlightsData(self, bounds):
    try:
      return self.fr_api.get_flights(bounds=bounds, flight_id=self.flight)
    except:
      return list()

  def visualize(self, f, details={}):
    alt = f.altitude
    ts  = f.time
    lat = f.latitude
    lng = f.longitude
    spd = f.ground_speed
    hd  = f.heading
    # conversions
    ts_ = time.strftime("%H:%M:%S", time.localtime(ts))
    alt_km = alt/3281
    spd_kmh = spd*1.852


    # auto-set zoom level according to flight altitude and speed
    self.zoom = max(8, int(16/(alt_km+2)+8))
    self.zoom += max(int(18-spd) // 10, 0)

    x,y = worldToPixel(lngToXWorld(lng), latToYWorld(lat), self.zoom)

    #line = f"{ts_}\t{alt}\t{lng:.4f}\t{lat:.4f}\t{spd}\t{hd}"
    tileLoc = f"Zoom: {self.zoom}"
    if 'trail' in details:
      tileLoc += f", History: {len(details['trail'])}"

    #print(line, "->", tileLoc)
    self.past_loc = (lat,lng)

    # update map tiles, returns new projection parameters onto them
    #self.center, offx, offy = self.tiles.update(x, y, self.zoom)
    self.latitude = x
    self.longitude = y
    self.tiles.update(x, y, self.zoom)
    trail = self.trails.update(details)

    if len(trail) >= 4:
      self.C.coords(self.trailPoly, trail)
      self.C.lift(self.trailPoly)
    
    # update position marker
    sx,sy = self.tiles.getPlanePos()

    # handle plane icon
    if self.icon:
      self.C.delete(self.icon)
    try:
      self.iconImage = self.sprites.getIcon(f, 80, None)
      self.icon = self.C.create_image((sx+3, sy+3), image=self.iconImage)
      self.C.lift(self.icon)
      if self.tiles.focus:
        self.C.lower(self.tiles.focus)
    except:
      self.C.moveto(self.tiles.focus, sx-5, sy-5)
      if self.tiles.focus:
        self.C.lift(self.tiles.focus)
      #pass

    # update Tooltips
    if "status" in details:
      aircraft_info = "N/A"
      if 'aircraft' in details and 'model' in details['aircraft'] and 'text' in details['aircraft']['model']:
          aircraft_info = details['aircraft']['model']['text']
      about = f"{f.callsign} ({f.airline_name})"
      about += f"\n\u2190 {f.origin_airport_name}"
      if 'time' in details and 'scheduled' in details['time']:
        dep_sch = time.strftime("%H:%M", time.localtime(details['time']['scheduled']['departure']))
        about += f"\n    {dep_sch}"
        if details['time']['real']['departure'] is not None:
          dep_real = time.strftime("%H:%M", time.localtime(details['time']['real']['departure']))
          about += f" (Real: {dep_real})"
        elif details['time']['estimated']['departure'] is not None:
          dep_est = time.strftime("%H:%M", time.localtime(details['time']['estimated']['departure']))
          about += f" (Est: {dep_est})"
      about += f"\n\u2192 {f.destination_airport_name}"
      if 'time' in details and 'scheduled' in details['time']:
        arr_sch = time.strftime("%H:%M", time.localtime(details['time']['scheduled']['arrival']))
        about += f"\n    {arr_sch}"
        if details['time']['real']['arrival'] is not None:
          arr_real = time.strftime("%H:%M", time.localtime(details['time']['real']['arrival']))
          about += f" (Real: {arr_real})"
        elif details['time']['estimated']['arrival'] is not None:
          arr_est = time.strftime("%H:%M", time.localtime(details['time']['estimated']['arrival']))
          about += f" (Est: {arr_est})"
      about += "\n"
      about += f"\nAircraft: {aircraft_info}"
      about += f"\nAltitude: {alt} ft ({alt_km:.2f} km)"
      about += f"\nGround Speed: {spd} kts ({spd_kmh:.0f} km/h)"
      
      status = details['status']['text']
      about += f"\nStatus: {status}"
      hist_len = 0 if 'trail' not in details else len(details['trail'])
      title = f"Follow Flight - {f.callsign} - {status} (Hist={hist_len},Z={self.zoom})"
      if details['status']['live']:
        title += "  **LIVE**"
      self.top.title(title)
    else:
      about = "Unknown"

    self.tts.updateTip(self.icon, about)

  def saveFlightDetails(self, details):
      try:
        l = len(details["trail"])
      except:
        return
      
      # try to give meaningful name if data are available
      try:
        ts = int(details["firstTimestamp"])
        airline = details["airline"]["code"]["iata"]
        orig = details["airport"]["origin"]["code"]["iata"]
        dest = details["airport"]["destination"]["code"]["iata"]
      except:
        filename = f"{self.flight}_details.json"
      else:
        filename = f"{time.strftime('%Y%m%d', time.localtime(ts))}_{airline}_{orig}>{dest}.json"

      if l > 0:
        with open(filename, 'w') as fp:
          json.dump(details, fp, sort_keys=True, indent=2)
        print(f"Flight details saved to file '{filename}'")

  def getLatestLoc(self, tau=0.01):
    lat,lng = self.past_loc
    bounds=f"{lat+tau:.3f},{lat-tau:.3f},{lng-tau:.3f},{lng+tau:.3f}"
    if tau < 0:
      bounds="77.879,-77.88,-180,180"

    found = False
    for f in self.getFlightsData(bounds):
      if f.id == self.flight:
        found = True
        lat = f.latitude
        lng = f.longitude
        ts  = f.time

        details = self.fr_api.get_flight_details(f)
        f.set_flight_details(details)

        # skip identical flight data
        if self.past_loc != (lat,lng):
          self.trails.new((ts,lat,lng))
          self.visualize(f, details)
        
        # store details
        self.past_details = details

        # update window icon (aircraft icon and heading)
        self.top.wm_iconphoto(False, self.iconImage)

    if not found:
      if tau < 0:
        #print("Object not found within bounds", bounds)
        ok = False
      elif tau < 10:
        ok = self.getLatestLoc(tau=tau*8)
      else:
        ok = self.getLatestLoc(tau=-1)
    else:
      ok = found

    return ok
  
  # main update loop
  def _update(self):
    self.top.update()
    
    ok = False
    try:
      ok = self.getLatestLoc()
    except Exception as e: # work on python 3.x
      print('Error:', str(e))

    details = self.past_details
    if self.online and not ok and self.saveHistory:
      self.saveFlightDetails(details)
    elif not self.online and self.past_details is None:
      print(f'Flight {self.flight} is offline!')
      f = Dict2Class(dict(id=self.flight))
      details = self.fr_api.get_flight_details(f)
      #self.visualize(f, details)
      if self.saveHistory:
        self.saveFlightDetails(details)
      #sys.exit()

    self.online = ok

    if not ok:
      try:
        callsign = details['identification']['callsign']
      except:
        callsign = "N/A"
      title = f"Follow Flight - {callsign} - OFFLINE"
      self.top.title(title)
      self.lost_count += 1
      if self.lost_count >= 10:
        print(f"Flight '{callsign}' ({self.flight}) turned offline. Bye bye!")
        return

    # update every 2 second
    timestep = self.timestep if self.online else self.timestep_lost

    delta = int((timestep-(time.time()-self.now))*1000)
    if delta < 10:
      # use current timestamp if processing latency is larger than timestep
      self.now = time.time()
      delta = 10
    else:
      # use timestep as increment to precicely synchronize to the continuous timeline
      self.now += timestep

    self.C.after(delta,self._update)
