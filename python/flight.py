'''
    helper class to handle airplane flights from FlightRadar24 histories or current locations
'''

from FlightRadar24_patch.api import FlightRadar24API
from hover import CanvasToolTip
import math
from coords import *
from helper import ft2km, kts2kmh, hsv2rgb, Dict2Class
from flight_ekf import FlightEKF
from constants import EKF_HEADING_THRESHOLD, EKF_RAW_TRAIL_LEN, EKF_EARTH_RADIUS_M
from logger import get_logger
import tkinter as tk
from threading import Thread
from followFlight import FollowFlight
import numpy as np
import time
from typing import Tuple, Optional

logger = get_logger(__name__)


def _rotate(matrix, degrees):
    rad = degrees*np.pi/180
    m_rot = np.array([[np.cos(rad), np.sin(rad)],[-np.sin(rad), np.cos(rad)]])
    return np.matmul(matrix, m_rot)


class FlightFactory:
    """
    Factory for creating fully initialized Flight objects.

    Usage:
        factory = FlightFactory(tk_root, fr_api, canvas, sprites)
        flight = factory.create(
            offsets=(offset_x, offset_y),
            zoom=11,
            max_flight_age=1200
        )
    """

    def __init__(self, tk_root, fr_api: FlightRadar24API, canvas: tk.Canvas, sprites,
                 enable_ekf: bool = True):
        """
        Initialize factory with shared dependencies.

        Args:
            tk_root: Tkinter root window
            fr_api: FlightRadar24 API instance
            canvas: Tkinter canvas for rendering
            sprites: Sprites instance for aircraft icons
            enable_ekf: Whether to enable EKF-based smooth animation
        """
        self._tk_root = tk_root
        self._fr_api = fr_api
        self._canvas = canvas
        self._sprites = sprites
        self._enable_ekf = enable_ekf

    def create(
        self,
        offsets: Tuple[int, int] = (0, 0),
        zoom: int = 11,
        max_flight_age: int = 900,
        centerview: bool = True
    ) -> 'Flight':
        """
        Create a fully initialized Flight instance.

        Args:
            offsets: (x, y) pixel offsets for positioning
            zoom: Map zoom level
            max_flight_age: Maximum age to keep flight data (seconds)
            centerview: Whether to center view on flight

        Returns:
            Fully initialized Flight object
        """
        flight = Flight(
            self._tk_root,
            self._fr_api,
            self._canvas,
            maxFlightAge=max_flight_age,
            centerview=centerview,
            enable_ekf=self._enable_ekf,
        )
        flight.init_offsets(offsets[0], offsets[1])
        flight.init_sprites(self._sprites)
        flight.init_zoom(zoom)
        return flight


class Flight(object):
  def __init__(self, tk_root, fr_api: FlightRadar24API, canvas: tk.Canvas, maxFlightAge=900, centerview=True,
               enable_ekf: bool = True):
    self.tk = tk_root
    self.fr_api = fr_api
    self.C = canvas
    self.past_loc = dict()
    self.past_alt = dict()
    self.temp_reduct = 0
    self.maxFlightAge = maxFlightAge
    self.off_x = 0
    self.off_y = 0
    self.xSize = int(canvas.__getitem__('width'))
    self.ySize = int(canvas.__getitem__('height'))
    self.about = None
    self.tts = None
    self.icon = None
    self.plane = None
    self.zoom = 11
    self.lifts = list()
    self.objects = list()
    self.last_ts = -1
    self.last_ping = -1
    self.history_loaded = False
    self.sprites = None  # Set via init_sprites or factory
    self._loading_details = False
    self._alive = True
    # EKF configuration
    self._enable_ekf: bool = enable_ekf
    # EKF position estimator (None when EKF disabled or not yet seeded)
    self.ekf: Optional[FlightEKF] = None
    # Rolling buffer of raw FR24 samples for multi-point velocity regression
    # Each entry: (time_s, lat, lng, speed_kts, heading_deg, alt_ft)
    self._raw_trail: list = []
    # Animation anchors — written by _render(), read by animate()
    self._anim_sx: Optional[float] = None
    self._anim_sy: Optional[float] = None
    self._anim_plane_id: Optional[int] = None
    self._anim_label_ids: list = []
    self._anim_render_hdg: float = 0.0
    self._anim_alt_km: float = 0.0
    self._anim_isize: float = 0.0
    self._anim_is_airborne: bool = False
    self._anim_aircraft_code: Optional[str] = None

  def cleanup(self):
    for o in self.objects:
      self.C.delete(o)
    if self.tts:
      self.tts.kill()
    self._anim_plane_id = None
    self._anim_label_ids = []
    self._anim_sx = None
    self._anim_sy = None

  def destroy(self):
    """Permanently remove this flight, preventing any pending callbacks from running."""
    self._alive = False
    self.cleanup()

  def init_offsets(self, off_x, off_y) -> None:
    self.off_x = off_x
    self.off_y = off_y

  def init_sprites(self, sprites) -> None:
    self.sprites = sprites

  def init_zoom(self, zoom) -> None:
    self.zoom = zoom

  def last_seen(self) -> None:
    return self.last_ts

  def lift_plane(self) -> None:
    if self.lifts:
      for l in self.lifts:
        self.C.lift(l)

  def onButton(self, id, fl=None):
    # Schedule on main thread — FollowFlight creates Tkinter widgets and must
    # not be called from a background thread.
    self.C.after(0, lambda: FollowFlight(self.tk, id, self.fr_api, initial_flight=fl))

  def update_about_content(self, fl, details):
    try:
      aircraft_info = details['aircraft']['model']['text']
    except (KeyError, TypeError):
      aircraft_info = "N/A"
    try:
      airline_name = fl.airline_name
    except AttributeError:
      airline_name = "N/A"
    try:
      origin_airport_name = fl.origin_airport_name
    except AttributeError:
      origin_airport_name = "N/A"
    try:
      destination_airport_name = fl.destination_airport_name
    except AttributeError:
      destination_airport_name = "N/A"
    self.about = f"{airline_name} ({aircraft_info})\n"\
      f"\u2190 {origin_airport_name}\n"\
      f"\u2192 {destination_airport_name}"

  def update(self, fl, now) -> None:
    if fl.time == self.last_ts:
      # no new data, leave update
      return

    # location and unit conversions
    sx, sy = latlngToPixel((fl.latitude, fl.longitude), self.zoom)
    sx += self.off_x
    sy += self.off_y
    alt_km = ft2km(fl.altitude)

    if self._enable_ekf:
      # Accumulate raw samples; multi-point regression reduces integer-second jitter
      self._raw_trail.append((float(fl.time), fl.latitude, fl.longitude,
                               float(fl.ground_speed), float(fl.heading),
                               float(fl.altitude)))
      if len(self._raw_trail) > EKF_RAW_TRAIL_LEN:
        del self._raw_trail[:-EKF_RAW_TRAIL_LEN]
      smooth_spd, smooth_hdg, valt_ft_s = self._smooth_velocity()
      # Initialize or update EKF
      if self.ekf is None:
        self.ekf = FlightEKF(fl.latitude, fl.longitude, smooth_hdg,
                             smooth_spd, fl.altitude, valt_ft_s)
      else:
        self.ekf.step(time.monotonic())   # predict to now before applying measurement
        self.ekf.update(fl.latitude, fl.longitude, smooth_hdg,
                        smooth_spd, fl.altitude, valt_ft_s)

    # append current position to trail
    self.past_loc[fl.time] = (sx, sy)
    self.past_alt[fl.time] = alt_km

    # clear old canvas objects
    self.cleanup()
    self.objects = list()
    self.lifts = list()
    self.tts = None

    # start background detail load for visible flights not yet loaded
    if sx >= -self.xSize/8 and sx < 9*self.xSize/8 and \
       sy >= -self.ySize/8 and sy < 9*self.ySize/8:
      if not self.history_loaded and not self._loading_details:
        self._loading_details = True
        Thread(target=self._load_details_bg, args=(fl,), daemon=True).start()

    self._render(fl, now)
    if self._enable_ekf:
      # _render() placed the icon at the raw FL position.  Immediately move it to
      # the EKF position so the canvas anchor always matches EKF state.  The EKF
      # corrected toward fl.lat via Kalman (with a gentle gain), so the delta here
      # is typically < 1 pixel.  This eliminates the jump that would otherwise
      # appear on the first animate() call after each new measurement.
      self._relocate_to_ekf()
    self.last_ts = fl.time

  def _relocate_to_ekf(self) -> None:
    """Move canvas items from the raw FR24 pixel position to the current EKF position.

    Called once per update, right after _render().  _render() draws the icon at
    fl.lat/fl.lng; the EKF (after its Kalman step) sits at a slightly different
    position because it blends prediction with measurement rather than snapping.
    By moving the items here the canvas anchor always equals pixel(ekf.lat, ekf.lng),
    so animate() produces only the expected tiny smooth increment on the next tick.
    """
    if self.ekf is None or self._anim_sx is None or self._anim_plane_id is None:
      return
    ekf_sx, ekf_sy = latlngToPixel((self.ekf.lat, self.ekf.lng), self.zoom)
    ekf_sx = float(ekf_sx + self.off_x)
    ekf_sy = float(ekf_sy + self.off_y)
    dx = ekf_sx - self._anim_sx
    dy = ekf_sy - self._anim_sy
    if abs(dx) > 0.01 or abs(dy) > 0.01:
      try:
        for lid in self._anim_label_ids:
          self.C.move(lid, dx, dy)
        self.C.move(self._anim_plane_id, dx, dy)
      except tk.TclError:
        return
    self._anim_sx = ekf_sx
    self._anim_sy = ekf_sy

  def _smooth_velocity(self) -> tuple:
    """
    Compute (speed_kts, heading_deg, valt_ft_s) from the raw trail buffer.

    Strategy:
    - Altitude:   linear regression over all buffered samples → smooth valt that
                  tolerates 25-ft quantisation and integer-second timestamps.
    - Speed:      circular-mean of recent FR24 ground_speed readings (transponder
                  value is reliable; averaging only removes update-to-update noise).
    - Heading:    when ≥3 samples spanning ≥2 s are available, blend a
                  position-regression direction with the circular-mean of measured
                  headings.  Position regression exploits sub-second precision
                  implicit in the real trajectory and is more stable than any
                  single FR24 heading sample.  If the two sources disagree by
                  more than 30° (manoeuvre, short trail) the measured heading wins.
    """
    N = len(self._raw_trail)
    if N == 0:
      return 0.0, 0.0, 0.0
    if N == 1:
      p = self._raw_trail[0]
      return p[3], p[4], 0.0   # speed_kts, heading, valt=0

    ts   = np.array([p[0] for p in self._raw_trail])
    lats = np.array([p[1] for p in self._raw_trail])
    lngs = np.array([p[2] for p in self._raw_trail])
    spds = np.array([p[3] for p in self._raw_trail])
    hdgs = np.array([p[4] for p in self._raw_trail])
    alts = np.array([p[5] for p in self._raw_trail])
    total_dt = ts[-1] - ts[0]

    # --- Vertical speed via least-squares (smoother than 2-point finite diff) ---
    if total_dt < 0.5:
      valt_ft_s = 0.0
    else:
      t_c   = ts - ts.mean()
      denom = float(np.dot(t_c, t_c))
      valt_ft_s = float(np.dot(t_c, alts - alts.mean()) / denom) if denom > 1e-9 else 0.0

    # --- Horizontal velocity ---
    # Circular mean of measured headings and arithmetic mean of speeds
    hdg_rad  = np.deg2rad(hdgs)
    meas_hdg = math.degrees(math.atan2(float(np.mean(np.sin(hdg_rad))),
                                        float(np.mean(np.cos(hdg_rad))))) % 360.0
    meas_spd = float(spds.mean())   # knots — trust transponder value

    if total_dt >= 2.0 and N >= 3:
      # Position-derived velocity via least-squares over the whole buffer
      t_c  = ts - ts.mean()
      denom = float(np.dot(t_c, t_c))
      vlat = float(np.dot(t_c, lats - lats.mean()) / denom)   # deg/s northward
      vlng = float(np.dot(t_c, lngs - lngs.mean()) / denom)   # deg/s eastward

      # Convert to m/s accounting for latitude scaling
      lat_rad = math.radians(float(lats.mean()))
      vlat_m  = vlat * (math.pi / 180.0) * EKF_EARTH_RADIUS_M
      vlng_m  = vlng * (math.pi / 180.0) * EKF_EARTH_RADIUS_M * math.cos(lat_rad)

      pos_speed_m_s = math.sqrt(vlat_m**2 + vlng_m**2)
      pos_hdg       = math.degrees(math.atan2(vlng_m, vlat_m)) % 360.0

      # Blend position-derived heading with measured heading when they agree
      hdg_diff = abs((pos_hdg - meas_hdg + 180.0) % 360.0 - 180.0)
      _KTS_TO_MS = 0.51444
      if pos_speed_m_s > _KTS_TO_MS * 20.0 and hdg_diff < 30.0:
        # Equal blend via circular mean of the two headings
        sin_h = math.sin(math.radians(pos_hdg)) + math.sin(math.radians(meas_hdg))
        cos_h = math.cos(math.radians(pos_hdg)) + math.cos(math.radians(meas_hdg))
        smooth_hdg = math.degrees(math.atan2(sin_h, cos_h)) % 360.0
      else:
        smooth_hdg = meas_hdg   # inconsistent (manoeuvre or sparse trail) — trust measurement
    else:
      smooth_hdg = meas_hdg   # too few / too close samples

    return meas_spd, smooth_hdg, valt_ft_s

  def _load_details_bg(self, fl) -> None:
    """Background thread: fetch flight details and schedule apply on main thread."""
    try:
      details = self.fr_api.get_flight_details(fl)
      fl.set_flight_details(details)
    except Exception as e:
      logger.error(f"Failed to get flight details: {e}")
      details = {}
    self.C.after(0, lambda: self._apply_details(fl, details))

  def _apply_details(self, fl, details) -> None:
    """Main thread callback: apply loaded trail history and re-render."""
    if not self._alive:
      return  # flight was removed before callback fired
    self._loading_details = False
    try:
      trail = sorted(details.get('trail', []), key=lambda x: x['ts'])
      self.past_loc = {}
      self.past_alt = {}
      now = time.time()
      for point in trail:
        ts_ = point['ts']
        if ts_ > now - self.maxFlightAge:
          sx_, sy_ = latlngToPixel((point['lat'], point['lng']), self.zoom)
          sx_ += self.off_x
          sy_ += self.off_y
          self.past_loc[ts_] = (sx_, sy_)
          self.past_alt[ts_] = ft2km(point['alt'])
      self.update_about_content(fl, details)
      self.history_loaded = True
    except Exception as e:
      logger.error(f"Failed to apply details: {e}")
    # re-render now that trail data is populated
    self.cleanup()
    self.objects = list()
    self.lifts = list()
    self.tts = None
    self._render(fl, time.time())

  def _render(self, fl, now) -> None:
    """Main thread: draw icon, labels, and trail for a flight."""
    id  = fl.id
    ori = fl.origin_airport_iata
    dst = fl.destination_airport_iata
    hdg = fl.heading

    sx, sy = latlngToPixel((fl.latitude, fl.longitude), self.zoom)
    sx += self.off_x
    sy += self.off_y
    alt_km = ft2km(fl.altitude)
    gsp_kmh = kts2kmh(fl.ground_speed)

    if sx >= -self.xSize/8 and sx < 9*self.xSize/8 and \
       sy >= -self.ySize/8 and sy < 9*self.ySize/8:

      # draw flight icon
      isize = 25 + alt_km*2
      self.icon = self.sprites.getIcon(fl, isize, alt_km, s=0.75, v=1.25)

      # draw description / details
      if alt_km > 0:
        # in the air
        y_off = isize//2
        try:
          plane = self.C.create_image([sx,sy], image=self.icon)
          self.tts = CanvasToolTip(self.C, plane, self.about, offset=(4,y_off))
        except (tk.TclError, AttributeError):
          # fallback to show plane position with a simple circle
          plane = self.C.create_oval([sx-5,sy-5,sx+5,sy+5], fill='#6688FF')

        self.objects.append(plane)
        self.C.tag_bind(plane, "<Button-2>", lambda event, id=id, fl=fl: self.onButton(id, fl))
        self.lifts.append(plane)

        # show details when being up in the air
        l1 = self.C.create_text([sx+2,sy+y_off+10], text=fl.callsign, font=('Helvetica','10'), fill='gray10')
        l2 = self.C.create_text([sx,sy+y_off+ 8], text=fl.callsign, font=('Helvetica','10'), fill='gold')
        l3 = self.C.create_text([sx,sy+y_off+20], text=f"{ori}\u2192{dst}", font=('Helvetica','8'), fill='gold')
        l4 = self.C.create_text([sx,sy+y_off+30], text=f"{alt_km:.2f}km | {gsp_kmh:.1f}km/h", font=('Helvetica','8'), fill='gold')
        self.lifts.extend([l1, l2, l3, l4])
        self.objects.extend([l1, l2, l3, l4])
        self._anim_plane_id    = plane
        self._anim_label_ids   = [l1, l2, l3, l4]
        self._anim_sx, self._anim_sy = float(sx), float(sy)
        self._anim_render_hdg  = float(fl.heading)
        self._anim_alt_km      = float(alt_km)
        self._anim_isize       = float(isize)
        self._anim_is_airborne = True
        self._anim_aircraft_code = getattr(fl, 'aircraft_code', None)
      else:
        # grounded
        arrow = np.array([[0,0.5],[1,1],[0,-1.5],[-1,1],[0,0.5]])
        poly = (_rotate(arrow, hdg)*4+[sx,sy]).reshape(-1)
        plane = self.C.create_polygon(*poly, fill='#ccaa00', outline='#181400')
        self.objects.append(plane)
        self.C.tag_bind(plane, "<Button-2>", lambda event, id=id, fl=fl: self.onButton(id, fl))
        self.lifts.append(plane)
        self._anim_plane_id    = plane
        self._anim_label_ids   = []
        self._anim_sx, self._anim_sy = float(sx), float(sy)
        self._anim_render_hdg  = float(fl.heading)
        self._anim_alt_km      = 0.0
        self._anim_is_airborne = False
        self._anim_aircraft_code = None   # polygon, can't itemconfigure image

        # make details accessible when grounded
        about = f"{fl.callsign}\n"\
                f"{ori}\u2192{dst}\n"\
                f"{alt_km:.2f}km | {gsp_kmh:.1f}km/h"
        self.tts = CanvasToolTip(self.C, plane, about, justify='center')

    self.draw_trail(now)

  def draw_trail(self, now) -> None:
    ''' Update trail
    '''
    # remove outdated samples
    for i in list(self.past_loc.keys()):
      if i < now - self.maxFlightAge:
        del self.past_loc[i]
        del self.past_alt[i]

    # draw flight trail
    timestamps = list(self.past_loc.keys())
    if len(timestamps) >= 2:
      for i, ts_ in enumerate(timestamps[:-1]):
        wid = int(round(self.past_alt[ts_]/2.5 + 1))
        h = math.fmod(self.past_alt[ts_]/12 + 0.25, 0.75)
        v = 0.5*(self.maxFlightAge-(now-ts_))/self.maxFlightAge + 0.4
        s = v/2
        col = hsv2rgb((h,s,v))
        pos1 = self.past_loc[ts_]
        pos2 = self.past_loc[timestamps[i+1]]
        if pos1[0] >= -self.xSize/8 and pos1[0] < 9*self.xSize/8 and \
           pos2[0] >= -self.xSize/8 and pos2[0] < 9*self.xSize/8 and \
           pos1[1] >= -self.ySize/8 and pos1[1] < 9*self.ySize/8 and \
           pos2[1] >= -self.ySize/8 and pos2[1] < 9*self.ySize/8:
          item = self.C.create_line([*pos1, *pos2], width=wid, fill=col)
          self.objects.append(item)
    
  def ping(self, now) -> None:
    ''' Update trail when no data was retrieved
    '''
    if now - self.last_ping < 20:
      # last ping came less than 20 seconds ago, no need to update trail
      return
    
    # remove all trail elements from canvas object list
    for o in self.objects:
      if self.C.type(o) == 'line':
        self.C.delete(o)

    # update trail with new current timestamp
    self.draw_trail(now)

    # save current timestamp as last ping timestamp
    self.last_ping = now

  def animate(self, now: float) -> None:
    """Fast-path: predict EKF, move canvas items. No full redraw."""
    if not self._alive or not self._enable_ekf or self.ekf is None or self._anim_plane_id is None:
      return
    if self._anim_sx is None:
      return
    # Guard — item may have been deleted by cleanup()
    try:
      self.C.type(self._anim_plane_id)
    except tk.TclError:
      self._anim_plane_id = None
      return

    self.ekf.step(now)

    sx_new, sy_new = latlngToPixel((self.ekf.lat, self.ekf.lng), self.zoom)
    sx_new += self.off_x
    sy_new += self.off_y
    dx = sx_new - self._anim_sx
    dy = sy_new - self._anim_sy

    if abs(dx) > 0.1 or abs(dy) > 0.1:
      try:
        for item_id in self._anim_label_ids:
          self.C.move(item_id, dx, dy)
        self.C.move(self._anim_plane_id, dx, dy)
      except tk.TclError:
        self._anim_plane_id = None
        return
      self._anim_sx = sx_new
      self._anim_sy = sy_new

    # Optionally regen icon if EKF heading has drifted enough
    if self._anim_is_airborne and self._anim_aircraft_code and self.sprites:
      hdg_ekf = self.ekf.heading
      delta = abs((hdg_ekf - self._anim_render_hdg + 180.0) % 360.0 - 180.0)
      if delta > EKF_HEADING_THRESHOLD:
        proxy = Dict2Class(dict(aircraft_code=self._anim_aircraft_code, heading=hdg_ekf))
        new_icon = self.sprites.getIcon(proxy, self._anim_isize,
                                        self._anim_alt_km, s=0.75, v=1.25)
        if new_icon is not None:
          try:
            self.C.itemconfigure(self._anim_plane_id, image=new_icon)
            self.icon = new_icon  # keep reference — Tkinter GC's unreferenced images
          except tk.TclError:
            pass
          self._anim_render_hdg = hdg_ekf

    self.lift_plane()
