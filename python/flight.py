'''
    helper class to handle airplane flights from FlightRadar24 histories or current locations
'''

from FlightRadar24_patch.api import FlightRadar24API
from hover import CanvasToolTip
from coords import *
import tkinter as tk
from threading import Thread
from followFlight import FollowFlight
import numpy as np

def _rotate(matrix, degrees):
    rad = degrees*np.pi/180
    m_rot = np.array([[np.cos(rad), np.sin(rad)],[-np.sin(rad), np.cos(rad)]])
    return np.matmul(matrix, m_rot)

class Flight(object):
  def __init__(self, tk_root, fr_api:FlightRadar24API, canvas:tk.Canvas, maxFlightAge=900, centerview=True):
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

  def cleanup(self):
    for o in self.objects:
      self.C.delete(o)
    if self.tts:
      self.tts.kill()

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

  def onButton(self, id):
    # create a thread
    thread = Thread(target=self.runFollowFlight, args=(id,))
    thread.setDaemon(True)
    thread.start()

  def runFollowFlight(self, id):
    # create toplevel and start followFlight app with given flight id
    #top_ = tk.Toplevel()
    FollowFlight(self.tk, id, self.fr_api)

  def ft2km(self, ft):
    return ft/3280.84
  
  def kts2kmh(self, kts):
    return kts*1.852
  
  def hsv2rgb(self, hsv):
      h,s,v = hsv
      
      h8 = h*8
      hi = int(h8)
      f  = h8 - hi
      
  #    p  = v * (1.0 - s)
  #    q  = v * (1.0 - s * f)
  #    t  = v * (1.0 - s * (1.0 - f))
      vs  = v * s
      vsf = vs * f
      p   = v - vs
      q   = v - vsf
      t   = v - vs + vsf
      
      if (hi == 0):
          r = v
          g = t
          b = p
      elif (hi == 1):
          r = q
          g = v
          b = p
      elif (hi == 2):
          r = p
          g = v
          b = t
      elif (hi == 3):
          r = p
          g = q
          b = v
      elif (hi == 4):
          r = t
          g = p
          b = v
      else:
          r = v
          g = p
          b = q
      
      #return np.array([r,g,b])
      return f"#{int(255*r):02X}{int(255*g):02X}{int(255*b):02X}"

  def update_about_content(self, fl, details):
    try:
      aircraft_info = details['aircraft']['model']['text']
    except:
      aircraft_info = "N/A"
    try:
      airline_name = fl.airline_name
    except:
      airline_name = "N/A"
    try:
      origin_airport_name = fl.origin_airport_name
    except:
      origin_airport_name = "N/A"
    try:
      destination_airport_name = fl.destination_airport_name
    except:
      destination_airport_name = "N/A"
    self.about = f"{airline_name} ({aircraft_info})\n"\
      f"\u2190 {origin_airport_name}\n"\
      f"\u2192 {destination_airport_name}"

  def update(self, fl, now) -> None:
    # get flight attributes
    id  = fl.id
    ts  = fl.time
    lng = fl.longitude
    lat = fl.latitude
    alt = fl.altitude
    ori = fl.origin_airport_iata
    dst = fl.destination_airport_iata
    gsp = fl.ground_speed
    hdg = fl.heading

    if ts == self.last_ts:
      # no new data, leave update
      return

    # location conversions
    sx, sy = latlngToPixel((lat,lng), self.zoom)
    # move flight pixel position into centered output window
    sx += self.off_x
    sy += self.off_y

    # unit conversions
    alt_km = self.ft2km(alt)
    gsp_kmh = self.kts2kmh(gsp)

    # delete old stuff
    self.cleanup()

    # initialize lists
    self.objects = list()
    self.lifts = list()
    self.tts = None

    #if id not in self.trails:
    #    self.trails[id] = Trails(self.fr_api, id, self.tiles, self.maxtrail, False)

    # get flight details and trail history
    ts_ = -1
    if sx >= -self.xSize/8 and sx < 9*self.xSize/8 and \
       sy >= -self.ySize/8 and sy < 9*self.ySize/8:
      if not self.history_loaded:
        details = self.fr_api.get_flight_details(fl)
        # FIXME: weird API loop, still required here??
        fl.set_flight_details(details)
        self.update_about_content(fl, details)

        # load trail history from details
        try:
          trail_details = details['trail']
        except Exception as e: 
          # No trail available
          pass
        else:
          self.past_loc = dict()
          self.past_alt = dict()
          trail_details = sorted(trail_details, key=lambda x: x['ts'])
          
          for trail in trail_details:
            ts_ = trail['ts']
            if ts_ not in self.past_loc and ts_ > now - self.maxFlightAge:
              sx_, sy_ = latlngToPixel((trail['lat'],trail['lng']), self.zoom)
              # move flight pixel position into centered output window
              sx_ += self.off_x
              sy_ += self.off_y
              if sx_ >= -self.xSize/8 and sx_ < 9*self.xSize/8 and \
                 sy_ >= -self.ySize/8 and sy_ < 9*self.ySize/8:
                self.past_loc[ts_] = (sx_, sy_)
                self.past_alt[ts_] = self.ft2km(trail['alt'])
        self.history_loaded = True
          
      # TODO: remove actual position when trail details are updated, this position may 
      # likely not be part of the trail history, for now, no updates are executed
      if ts > ts_:
        # append last position when newer than those in trail history
        self.past_loc[ts] = (sx, sy)
        self.past_alt[ts] = alt_km
      else:
        sx, sy = sx_, sy_

      # draw flight icon
      isize = 25 if alt_km < 3 else 30 if alt_km < 9 else 35
      icolor = 'R' if ori == "N/A" or dst == "N/A" else 'B' if alt_km > 12.0 else 'Y'
      self.icon = self.sprites.getIcon(fl, isize, icolor)

      # draw description / details
      if alt_km > 0:
        # in the air
        try:
          plane = self.C.create_image([sx,sy], image=self.icon)
          self.tts = CanvasToolTip(self.C, plane, self.about)
        except:
          # fallback to show plane position with a simple circle
          plane = self.C.create_oval([sx-5,sy-5,sx+5,sy+5], fill='#6688FF')

        self.objects.append(plane)
        self.C.tag_bind(plane, "<Button-2>", lambda event, id=id: self.onButton(id))
        self.lifts.append(plane)

        # show details when being up in the air
        l1 = self.C.create_text([sx+2,sy+20], text=fl.callsign, font=('Helvetica','10'), fill='gray10')
        l2 = self.C.create_text([sx,sy+18], text=fl.callsign, font=('Helvetica','10'), fill='gold')
        l3 = self.C.create_text([sx,sy+30], text=f"{ori}\u2192{dst}", font=('Helvetica','8'), fill='gold')
        l4 = self.C.create_text([sx,sy+40], text=f"{alt_km:.2f}km | {gsp_kmh:.1f}km/h", font=('Helvetica','8'), fill='gold')
        self.lifts.extend([l1, l2, l3, l4])
        self.objects.extend([l1, l2, l3, l4])
      else:
        # grounded
        #plane = self.C.create_oval([sx-3,sy-3,sx+3,sy+3], fill='#EEAA00')
        arrow = np.array([[0,0.5],[1,1],[0,-1.5],[-1,1],[0,0.5]])
        poly = (_rotate(arrow, hdg)*4+[sx,sy]).reshape(-1)
        plane = self.C.create_polygon(*poly, fill='#ccaa00', outline='#181400')
        self.objects.append(plane)
        self.C.tag_bind(plane, "<Button-2>", lambda event, id=id: self.onButton(id))
        self.lifts.append(plane)

        # make details accessible when grounded
        about = f"{fl.callsign}\n"\
                f"{ori}\u2192{dst}\n"\
                f"{alt_km:.2f}km | {gsp_kmh:.1f}km/h"
        self.tts = CanvasToolTip(self.C, plane, about, justify='center')

#      logo_path = f"logos/{fl.airline_iata}_{fl.airline_icao}.png"
#      if os.path.exists(logo_path):
#        with open(logo_path, 'rb') as f:
#          logo = f.read()
#      else:
#        try:
#          logo = self.fr_api.get_airline_logo(fl.airline_iata, fl.airline_icao)
#        except:
#          logo = None
#        finally:
#          if logo is not None and logo[1] == 'png':
#            with open(logo_path, 'wb') as f:
#              f.write(logo[0])
#            logo = logo[0]
      #if logo is not None:
      #  logo_img = Image.open(io.BytesIO(logo))
      #  logo_width, logo_height = logo_img.size
      #  logo_image = ImageTk.PhotoImage(logo_img.resize((logo_width*16//logo_height, 16)))
      #  #logo_image = ImageTk.PhotoImage(logo_img)
      #  lifts.append(self.C.create_image([sx,sy+20], image=logo_image, tags=is))

    self.draw_trail(now)

    # save timestamp of last update
    self.last_ts = ts

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
        col = self.hsv2rgb((h,s,v))
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
