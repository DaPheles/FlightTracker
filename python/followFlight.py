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
from flight_ekf import FlightEKF
from constants import EKF_RAW_TRAIL_LEN, EKF_EARTH_RADIUS_M
from logger import get_logger
from config_manager import get_config
import tkinter as tk
import numpy as np
import time, json, sys, threading

logger = get_logger(__name__)

class FollowFlight:
  def __init__(self, tk_root, flight, fr_api=None, saveHistory=False, destroyEvent=None, initial_flight=None) -> None:
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
    self.enableEkf = app_cfg.enable_ekf
    self._anim_interval_ms = max(50, int(1000.0 / app_cfg.animation_rate))

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

    # EKF state (disabled for ISS — its update rate is already 0.25 s)
    self.ekf: FlightEKF = None
    self._raw_trail_ekf: list = []

    self.now = time.time()
    self.past_loc = (initial_flight.latitude, initial_flight.longitude) \
        if initial_flight is not None else self.home
    self.past_details = None
    self.lost_count = 0
    self._initial_flight = initial_flight

    # async fetch state (non-ISS mode)
    self._fetching = False
    self._pending_result = None

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
    if initial_flight is not None:
      initX, initY = worldToPixel(lngToXWorld(initial_flight.longitude),
                                   latToYWorld(initial_flight.latitude), self.zoom)
    else:
      initX, initY = latlngToPixel(self.home, self.zoom)
    self.tiles.update(initX, initY, self.zoom, force=True)

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
    self.C.after(0, self._update)
    if self.enableEkf and not self.iss_mode:
      self.C.after(self._anim_interval_ms, self._anim_loop)
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

  def _fetch_bg(self):
    """Background thread: locate flight with expanding bounds and fetch details."""
    result = {'ok': False, 'f': None, 'details': None, 'ts': None, 'lat': None, 'lng': None}
    try:
      lat, lng = self.past_loc
    except (TypeError, ValueError):
      self._pending_result = result
      self._fetching = False
      return

    tau = 0.01
    found = False
    while True:
      if tau < 0:
        bounds = "77.879,-77.88,-180,180"
      else:
        bounds = f"{lat+tau:.3f},{lat-tau:.3f},{lng-tau:.3f},{lng+tau:.3f}"

      for f in self.getFlightsData(bounds):
        if f.id == self.flight:
          found = True
          f_lat = f.latitude
          f_lng = f.longitude
          f_ts  = f.time
          self.flight_icao = f.icao_24bit

          # supplement with local ADS-B receiver if available
          if self.sa_api and self.flight_icao and self.past_details is not None:
            try:
              sa_data = self.update_sa(self.flight_icao)
              if sa_data is not None and sa_data[0] > f_ts + 0.11:
                f_ts, f_lat, f_lng = sa_data
            except Exception:
              pass

          try:
            details = self.fr_api.get_flight_details(f)
            f.set_flight_details(details)
          except Exception:
            details = {}

          result['ok']      = True
          result['f']       = f
          result['details'] = details
          result['ts']      = f_ts
          result['lat']     = f_lat
          result['lng']     = f_lng
          break

      if found:
        break
      if tau < 0:
        break
      elif tau < 10:
        tau *= 8
      else:
        tau = -1

    self._pending_result = result
    self._fetching = False

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

    self.past_loc = (lat, lng)

    # EKF update: seed or correct the predictor with the new FR24 measurement
    if self.enableEkf:
      self._raw_trail_ekf.append((float(f.time), f.latitude, f.longitude,
                                   float(f.ground_speed), float(f.heading),
                                   float(f.altitude)))
      if len(self._raw_trail_ekf) > EKF_RAW_TRAIL_LEN:
        del self._raw_trail_ekf[:-EKF_RAW_TRAIL_LEN]
      smooth_spd, smooth_hdg, valt_ft_s = self._smooth_velocity_ff()
      if self.ekf is None:
        self.ekf = FlightEKF(f.latitude, f.longitude, smooth_hdg,
                             smooth_spd, f.altitude, valt_ft_s)
      else:
        self.ekf.step(time.monotonic())
        self.ekf.update(f.latitude, f.longitude, smooth_hdg,
                        smooth_spd, f.altitude, valt_ft_s)

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

  def _anim_loop(self) -> None:
    """High-frequency EKF animation — smooth map panning (centerview) or icon movement."""
    if not self.is_alive:
      return
    if self.ekf is not None and self.icon is not None:
      self.ekf.step(time.monotonic())
      ekf_x, ekf_y = worldToPixel(lngToXWorld(self.ekf.lng),
                                   latToYWorld(self.ekf.lat), self.zoom)
      # tiles.update() repositions tile images (no new downloads unless tile index changes)
      self.tiles.update(ekf_x, ekf_y, self.zoom)
      sx, sy = self.tiles.getPlanePos()
      try:
        self.C.coords(self.icon, sx, sy)
      except tk.TclError:
        pass
    self.C.after(self._anim_interval_ms, self._anim_loop)

  def _smooth_velocity_ff(self) -> tuple:
    """Compute (speed_kts, heading_deg, valt_ft_s) from the raw EKF trail buffer.

    Mirrors Flight._smooth_velocity() — linear regression for valt, position-regression
    heading blended with measured heading for smoother inter-update EKF predictions.
    """
    trail = self._raw_trail_ekf
    N = len(trail)
    if N == 0:
      return 0.0, 0.0, 0.0
    if N == 1:
      p = trail[0]
      return p[3], p[4], 0.0   # speed_kts, heading, valt=0

    ts   = np.array([p[0] for p in trail])
    lats = np.array([p[1] for p in trail])
    lngs = np.array([p[2] for p in trail])
    spds = np.array([p[3] for p in trail])
    hdgs = np.array([p[4] for p in trail])
    alts = np.array([p[5] for p in trail])
    total_dt = ts[-1] - ts[0]

    # Vertical speed via least-squares
    if total_dt < 0.5:
      valt_ft_s = 0.0
    else:
      t_c   = ts - ts.mean()
      denom = float(np.dot(t_c, t_c))
      valt_ft_s = float(np.dot(t_c, alts - alts.mean()) / denom) if denom > 1e-9 else 0.0

    # Horizontal: circular mean of measured headings + position regression blend
    hdg_rad  = np.deg2rad(hdgs)
    meas_hdg = math.degrees(math.atan2(float(np.mean(np.sin(hdg_rad))),
                                        float(np.mean(np.cos(hdg_rad))))) % 360.0
    meas_spd = float(spds.mean())

    if total_dt >= 2.0 and N >= 3:
      t_c  = ts - ts.mean()
      denom = float(np.dot(t_c, t_c))
      vlat = float(np.dot(t_c, lats - lats.mean()) / denom)
      vlng = float(np.dot(t_c, lngs - lngs.mean()) / denom)
      lat_rad = math.radians(float(lats.mean()))
      vlat_m  = vlat * (math.pi / 180.0) * EKF_EARTH_RADIUS_M
      vlng_m  = vlng * (math.pi / 180.0) * EKF_EARTH_RADIUS_M * math.cos(lat_rad)
      pos_speed_m_s = math.sqrt(vlat_m**2 + vlng_m**2)
      pos_hdg       = math.degrees(math.atan2(vlng_m, vlat_m)) % 360.0
      hdg_diff = abs((pos_hdg - meas_hdg + 180.0) % 360.0 - 180.0)
      _KTS_TO_MS = 0.51444
      if pos_speed_m_s > _KTS_TO_MS * 20.0 and hdg_diff < 30.0:
        sin_h = math.sin(math.radians(pos_hdg)) + math.sin(math.radians(meas_hdg))
        cos_h = math.cos(math.radians(pos_hdg)) + math.cos(math.radians(meas_hdg))
        smooth_hdg = math.degrees(math.atan2(sin_h, cos_h)) % 360.0
      else:
        smooth_hdg = meas_hdg
    else:
      smooth_hdg = meas_hdg

    return meas_spd, smooth_hdg, valt_ft_s

  def _show_initial(self, fl) -> None:
    """Show plane icon at known position immediately — no trail, no API call."""
    lat = fl.latitude
    lng = fl.longitude
    alt_km = ft2km(fl.altitude)
    spd = fl.ground_speed  # knots — same units used in visualize()

    self.zoom = max(8, int(16 / (alt_km + 2) + 8))
    self.zoom += max(int(18 - spd) // 10, 0)
    self.zoom += self.zoom_offset

    x, y = worldToPixel(lngToXWorld(lng), latToYWorld(lat), self.zoom)
    self.latitude = x
    self.longitude = y
    self.tiles.update(x, y, self.zoom)

    sx, sy = self.tiles.getPlanePos()
    if self.icon:
      self.C.delete(self.icon)
    try:
      self.iconImage = self.sprites.getIcon(fl, 80, alt_km)
      self.icon = self.C.create_image((sx, sy), image=self.iconImage)
      self.C.lift(self.icon)
      if self.tiles.focus:
        self.C.lower(self.tiles.focus)
    except (tk.TclError, AttributeError, KeyError):
      self.icon = None
    self.top.update()

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

      # Immediate pre-display using the flight object we already had at click time
      if self._initial_flight is not None:
        self._show_initial(self._initial_flight)
        self._initial_flight = None

      # start background fetch if idle
      if not self._fetching:
        self._fetching = True
        threading.Thread(target=self._fetch_bg, daemon=True).start()

      # process pending result on main thread
      if self._pending_result is not None:
        result = self._pending_result
        self._pending_result = None
        ok = result['ok']

        if ok:
          lat, lng = result['lat'], result['lng']
          if self.past_loc != (lat, lng):
            self.trails.new((result['ts'], lat, lng))
            self.visualize(result['f'], result['details'])
          self.top.wm_iconphoto(False, self.iconImage)
          self.top.iconphoto(False, self.iconImage)
          self.past_details = result['details']

        details = self.past_details
        if self.online and not ok and self.saveHistory:
          self.saveFlightDetails(details)
        elif not self.online and self.past_details is None:
          logger.info(f'Flight {self.flight} is offline!')
          f = Dict2Class(dict(id=self.flight))
          details = self.fr_api.get_flight_details(f)
          if self.saveHistory:
            self.saveFlightDetails(details)

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

    # update every 2 seconds; only slow down once we have confirmed a miss
    timestep = self.timestep if (self.online or self.lost_count == 0) else self.timestep_lost

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
