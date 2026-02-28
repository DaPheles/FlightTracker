'''
    Application to follow flights using FlightRadar24 API and Google Maps tiles
'''

from FlightRadar24_patch.api import FlightRadar24API
from hover import CanvasToolTip
from sprites import Sprites
from tiles import Tiles
from trails import Trails
from coords import *
from helper import Dict2Class, ft2km, kts2kmh
from iss import IssAPI
from skyaware import SkyawareAPI
from logger import get_logger
from config_manager import get_config
import tkinter as tk
import time, json, sys

logger = get_logger(__name__)

class FollowFlight:
  def __init__(self, tk_root, flight, fr_api=None, saveHistory=False, destroyEvent=None) -> None:
    self.tk = tk_root
    self.top = tk.Toplevel()
    self.top.title("Follow Flight")
    self.top.resizable(False,False)
    if destroyEvent is not None:
      self.top.protocol("WM_DELETE_WINDOW", destroyEvent)
    else:
      self.top.protocol("WM_DELETE_WINDOW", self._destroy)

    # Load configuration
    config = get_config()
    home_cfg = config.home
    app_cfg = config.follow_flight

    # Apply configuration
    self.home = home_cfg.location
    self.zoom = home_cfg.zoom
    self.zoom_offset = 0
    self.localeLang = home_cfg.locale_lang
    self.localeCountry = home_cfg.locale_country

    self.mapGrid = app_cfg.grid
    self.mapTiles = dict(
        basemap=app_cfg.map_tiles.basemap,
        roadmap=app_cfg.map_tiles.roadmap,
        brightness=app_cfg.map_tiles.brightness
    )
    self.tileSize = 256  # fixed tile size
    self.centerview = app_cfg.centerview
    self.maxtrail = app_cfg.max_trail
    self.enableRadar = app_cfg.enable_rain_radar
    self.enableClouds = app_cfg.enable_cloud_radar

    # load sprites
    self.sprites = Sprites()
    self.iconImage = None
    self.icon = None

    self.f = None
    self.flight = None
    self.flight_icao = None
    self.fr_api = None
    self.sa_api = None
    self.iss_api = None
    self.iss_mode = False
    if flight == 'iss':
      self.iss_api = IssAPI()
      self.saveHistory = False
      self.iss_mode = True
      self.timestep = 0.25        ;# in seconds
      self.online = True
      self.top.title("Follow Flight - ISS  **LIVE**")
      f = Dict2Class(dict(aircraft_code='ISS', heading=45))
      try:
        self.iconImage = self.sprites.getIcon(f, 80, alt=7.25, s=0.5, v=2.0)
        self.top.wm_iconphoto(False, self.iconImage)
        self.top.iconphoto(False, self.iconImage)
      except (tk.TclError, AttributeError, KeyError):
        pass
    else:
      self.flight = flight
      self.fr_api = fr_api if fr_api else FlightRadar24API()
      self.saveHistory = saveHistory
#      self.timestep = 3.2         ;# in seconds
      self.timestep = 2.0         ;# in seconds
      self.timestep_lost = 15.0   ;# in seconds
      self.online = False
      self.sa_api = SkyawareAPI()

    self.now = time.time()
    self.past_loc = self.home
    self.past_details = None
    self.lost_count = 0

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
    if self.iss_mode:
      self.trails.updateTS = 0
      self.trails.timegap = 8


    # prepare initial trail trace
    self.trailPoly = self.C.create_line([0,0,0,0], fill="#AA8866", width=5, smooth=1)
    self.tts = CanvasToolTip(self.C, self.trailPoly, "")

    # start periodic update cycles
    self.top.bind('<KeyPress>', self.onKey)
    self.C.after(0,self._update)
    self.is_alive = True

  def _destroy(self):
    # try to close both: toplevel window and Followflight class to prevent more updates in undefined states
    self.is_alive = False
    try:
      self.top.destroy()
    except tk.TclError:
      pass

  def onKey(self, event):
    if event.char == "c":
      self.tiles.toggleClouds()
      self.tiles.update(self.latitude, self.longitude, self.zoom, force=True)
      self.top.update()
    elif event.char == "r":
      self.tiles.toggleRadar()
      self.tiles.update(self.latitude, self.longitude, self.zoom, force=True)
      self.top.update()
    elif event.char == '+':
      self.zoom += 1
      self.zoom_offset += 1
      self.tiles.update(self.latitude, self.longitude, self.zoom)
      self.top.update()
    elif event.char == '-':
      self.zoom -= 1
      self.zoom_offset -= 1
      self.tiles.update(self.latitude, self.longitude, self.zoom)
      self.top.update()

  def getFlightsData(self, bounds):
    try:
      return self.fr_api.get_flights(bounds=bounds, flight_id=self.flight)
    except Exception:
      return list()

  def visualize(self, f, details={}):
    alt = f.altitude
    #ts  = f.time
    lat = f.latitude
    lng = f.longitude
    spd = f.ground_speed
    #hd  = f.heading
    icao = f.icao_24bit
    # conversions
    alt_km = ft2km(alt)
    spd_kmh = kts2kmh(spd)

    #print("=== Status ===")
    #for k,v in zip(f.__dict__.keys(), f.__dict__.values()):
    #  print(k,v)

    # auto-set zoom level according to flight altitude and speed
    self.zoom = max(8, int(16/(alt_km+2)+8))
    self.zoom += max(int(18-spd) // 10, 0)
    self.zoom += self.zoom_offset

    x,y = worldToPixel(lngToXWorld(lng), latToYWorld(lat), self.zoom)

    tileLoc = f"Zoom: {self.zoom}"
    if 'trail' in details:
      tileLoc += f", History: {len(details['trail'])}"

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
      self.iconImage = self.sprites.getIcon(f, 80, 7.25)
      self.icon = self.C.create_image((sx, sy), image=self.iconImage)
      self.C.lift(self.icon)
      if self.tiles.focus:
        self.C.lower(self.tiles.focus)
    except (tk.TclError, AttributeError, KeyError):
      self.C.moveto(self.tiles.focus, sx-5, sy-5)
      if self.tiles.focus:
        self.C.lift(self.tiles.focus)

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
      except (KeyError, TypeError):
        logger.warning("Flight details are not available!")
        return

      # try to give meaningful name if data are available
      try:
        ts = int(details["firstTimestamp"])
        airline = details["airline"]["code"]["iata"]
        orig = details["airport"]["origin"]["code"]["iata"]
        dest = details["airport"]["destination"]["code"]["iata"]
      except (KeyError, TypeError):
        filename = f"{self.flight}_details.json"
      else:
        filename = f"{time.strftime('%Y%m%d', time.localtime(ts))}_{airline}_{orig}>{dest}.json"

      if l > 0:
        with open(filename, 'w') as fp:
          json.dump(details, fp, sort_keys=True, indent=2)
        logger.info(f"Flight details saved to file '{filename}'")
      else:
        #flight_details = self.fr_api.get_history_data(self.flight, 'kml', time.time())
        #print(ts)
        logger.debug(f"Details: {details}")
        logger.warning("Flight trail is not available! Try getting playback data...")
        f = Dict2Class(dict(id=self.flight))
        ts = 1732498800
        flight_playback = self.fr_api.get_flight_playback(f, ts)
        with open(filename, 'w') as fp:
          json.dump(flight_playback, fp, sort_keys=True, indent=2)
        logger.info(f"Playback details saved to file '{filename}'")

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
        self.flight_icao = f.icao_24bit

        # update skyaware if available
        if self.sa_api and self.flight_icao and self.past_details is not None:
          sa_data = self.update_sa(self.flight_icao)
          if sa_data is not None and sa_data[0] > ts + 0.11:
            ts, lat, lng = sa_data
            #print("SA",self.flight_icao,lat,lng,sa_data[0])

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
        self.top.iconphoto(False, self.iconImage)

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
  
  def visualize_iss(self, ts, lat, lng):
    self.zoom = 6 # default ISS zoom

    x,y = worldToPixel(lngToXWorld(lng), latToYWorld(lat), self.zoom)

    self.past_loc = (lat,lng)

    self.latitude = x
    self.longitude = y
    self.tiles.update(x, y, self.zoom)
    trail = self.trails.update()

    if len(trail) >= 4:
      self.C.coords(self.trailPoly, trail)
      self.C.lift(self.trailPoly)
    
    # update position marker
    sx,sy = self.tiles.getPlanePos()

    # handle plane icon
    if self.icon:
      self.C.delete(self.icon)
    
    # try to get sprite
    f = Dict2Class(dict(aircraft_code='ISS', heading=45))
    if self.iconImage is None:
      self.C.moveto(self.tiles.focus, sx-5, sy-5)
      if self.tiles.focus:
        self.C.lift(self.tiles.focus)
    else:
      self.icon = self.C.create_image((sx, sy), image=self.iconImage)
      self.C.lift(self.icon)
      if self.tiles.focus:
        self.C.lower(self.tiles.focus)

  # main update loop
  def _update(self):
    if self.iss_mode:
      response = self.iss_api.get_position()

      ts = int(response[0])
      lat = float(response[1])
      lng = float(response[2])

      self.trails.new((ts,lat,lng))
      self.visualize_iss(ts, lat, lng)

    else:

      ok = False
      try:
        ok = self.getLatestLoc()
      except Exception:
        pass

      details = self.past_details
      if self.online and not ok and self.saveHistory:
        self.saveFlightDetails(details)
      elif not self.online and self.past_details is None:
        logger.info(f'Flight {self.flight} is offline!')
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
        except (KeyError, TypeError):
          callsign = "N/A"
        title = f"Follow Flight - {callsign} - OFFLINE"
        try:
          self.top.title(title)
        except tk.TclError:
          pass
        self.lost_count += 1
        if self.lost_count >= 10:
          logger.info(f"Flight '{callsign}' ({self.flight}) turned offline. Bye bye!")
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

    # commit suicide if no longer needed
    if self.is_alive:
      self.top.update()
      self.C.after(delta,self._update)
    else:
      self._destroy()
      # TODO: who's gonna clean up after this??

  def update_sa(self, flight_icao):
    self.sa_api.update()
    f = self.sa_api.get_flights(flight_icao)
    if f is None:
      return
    
    #print(f)
    if 'lat' in f and 'lng' in f:
      #x,y = latlngToPixel((f['lat'], f['lng']), self.zoom)
      #print(" =>", x,y, x-self.latitude, y-self.longitude, self.tiles.offset)
      logger.debug(f"Skyaware data: {f}")
      return f['time'], f['lat'], f['lng']
    
    return None
