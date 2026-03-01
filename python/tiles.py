'''
    handle map tiles
'''

import time
import threading
from PIL import Image, ImageTk
from coords import *
from wettercom import WetterComAPI
from googlemaps import GoogleMapsAPI
import numpy as np

CLOUDS_ALPHA = 0.6
DEBUG = False
MAX_PIL_CACHE = 128   # composited tile images kept in memory


class Tiles(object):
    def __init__(self, canvas, tileSize: int, tileNum, style: dict, zoom, home, centerview=True):
        self.C = canvas
        self.tileSize_ = tileSize
        self.tileNum_ = tileNum
        self.style = style
        # bgImg: (tx,ty,z) -> ImageTk.PhotoImage  — keeps Tkinter reference alive
        # tiles: (tx,ty,z) -> canvas item id
        self.bgImg = dict()
        self.tiles = dict()
        self.zoom_ = zoom
        self.centerview = centerview

        self.homeX_, self.homeY_ = latlngToPixel(home, zoom)
        self.center_ = None
        self.offset_ = None
        self.homeRadarIndex_ = 0

        self.localeLang = 'en'
        self.localeCountry = 'GB'
        self.enableClouds = False
        self.enableRadar = False

        self.wc = WetterComAPI()
        self.gm = GoogleMapsAPI()

        self.focus_ = None
        if centerview:
            sx = tileNum[0] * tileSize / 2
            sy = tileNum[1] * tileSize / 2
            self.focus_ = self.C.create_oval(
                [sx - 5, sy - 5, sx + 5, sy + 5], fill='#FFAA66', tags='home', width=2
            )

        # in-memory composited PIL image cache: (tx, ty, z, ts_5min) -> PIL Image
        self._pil_cache: dict = {}
        self._cfg_sig = None        # (basemap, roadmap, brightness, clouds, radar)
        self._refresh_gen: int = 0  # incremented each refreshTiles call
        self._required_keys: set = set()   # (tx,ty,z) currently expected on canvas
        self._tile_ts: int = 0      # ts_5min used in last refreshTiles

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def tileSize(self):
        return self.tileSize_

    @property
    def tileNum(self):
        return self.tileNum_

    @property
    def zoom(self):
        return self.zoom_

    @property
    def center(self):
        return self.center_

    @property
    def offset(self):
        return self.offset_

    @property
    def focus(self):
        return self.focus_

    @property
    def homeRadarIndex(self):
        return self.homeRadarIndex_

    def toggleClouds(self):
        self.enableClouds = not self.enableClouds

    def toggleRadar(self):
        self.enableRadar = not self.enableRadar

    def setLocale(self, lang, country):
        self.localeLang = lang
        self.localeCountry = country
        if self.wc:
            self.wc.setLocale(lang, country)
        if self.gm:
            self.gm.setLocale(lang, country)

    # ------------------------------------------------------------------
    # Tile image composition (unchanged public API)
    # ------------------------------------------------------------------
    def getTile(self, x, y, z, ts=None):
        '''
        Downloads a map tile image and store in tile cache. If already available, load the stored image.

        @param x the x value of the world coordinate
        @param y the y value of the world coordinate
        @param z the zoom level of the world coordinate

        @return the binary image data
        '''
        x = x % (2 ** z)
        if y < 0 or y >= 2 ** z:
            return Image.fromarray(np.full((self.tileSize_, self.tileSize_), 128, dtype=np.uint8))

        img = self.gm.getTileImage(x, y, z, self.tileSize_, self.style['basemap'], debug=DEBUG)
        if self.style['roadmap']:
            img_overlay = self.gm.getTileImage(x, y, z, self.tileSize_, 'roadmap', debug=DEBUG)
            img.paste(img_overlay, (0, 0), img_overlay)

        # brightness adjust
        img_ = np.array(img)
        img_[:, :, :3] = (img_[:, :, :3] * self.style['brightness']).astype(np.uint8)
        img = Image.fromarray(img_)

        # render cloud radar overlay with zoom levels smaller or equal 13 only
        if self.enableClouds and z <= 13:
            if DEBUG: print(f"Tiles::getTile(): Trying to get cloud image for x={x}, y={y}, z={z}")
            img_overlay = self.wc.getCloudImage(x, y, z)
            if img_overlay:
                img_overlay_ = np.array(img_overlay).astype(np.float32)
                img_overlay_[:, :, 3] -= img_overlay_[:, :, 3] * (1 - CLOUDS_ALPHA)
                img_overlay = Image.fromarray(img_overlay_.astype(np.uint8))

                img = Image.fromarray(img_)
                img.paste(img_overlay, (0, 0), img_overlay)
                img_ = np.array(img)

        # render rain radar overlay with zoom levels smaller or equal 13 only
        if self.enableRadar and z <= 13:
            if ts is None:
                ts_ = int(time.time())
            else:
                ts_ = ts
            ts_ = ts_ - (ts_ % 300)  # 5 min granularity

            self.wc.setRadarTimestamp(ts_)

            if DEBUG: print(f"Tiles::getTile(): Trying to get radar image for x={x}, y={y}, z={z}, ts={ts_}")
            img_overlay = self.wc.getRadarImage(x, y, z, ts_)
            if img_overlay:
                # returned image is 512x512, needs further subtiling!
                tilex, tiley = 256 * (x % 2), 256 * (y % 2)

                img_overlay = img_overlay.crop((tilex, tiley, tilex + 256, tiley + 256))
                img_overlay_ = np.array(img_overlay).astype(np.uint16)

                # get radar index of home location
                if x == self.homeX_ // 256 and y == self.homeY_ // 256:
                    self.homeRadarIndex_ = img_overlay_[self.homeY_ % 256, self.homeX_ % 256, 2]

                img_[:, :, 0] = np.clip(img_[:, :, 0].astype(np.int16) -
                                        img_overlay_[:, :, 2], 0, 255).astype(np.uint8)
                img_[:, :, 1] = np.clip(img_[:, :, 1].astype(np.int16) -
                                        img_overlay_[:, :, 2], 0, 255).astype(np.uint8)
                img_[:, :, 2] = np.clip(img_[:, :, 2].astype(np.int16) +
                                        img_overlay_[:, :, 2] * 4, 0, 255).astype(np.uint8)
                img = Image.fromarray(img_)

        return img

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _cfg_signature(self):
        '''Return a tuple that uniquely identifies the current rendering config.'''
        return (
            self.style['basemap'],
            self.style.get('roadmap', False),
            self.style.get('brightness', 1.0),
            self.enableClouds,
            self.enableRadar,
        )

    def _tile_screen_pos(self, tx, ty):
        '''
        Compute screen top-left (x, y) for tile (tx, ty) given current center and offset.
        Returns None if center is not yet set.
        '''
        if self.center_ is None or self.offset_ is None:
            return None
        tileSize = self.tileSize_
        tileNum = self.tileNum_
        shiftX = tileNum[0] // 2
        shiftY = tileNum[1] // 2
        cx, cy = self.center_
        offx, offy = self.offset_
        screen_x = (tx - cx + shiftX) * tileSize - offx
        screen_y = (ty - cy + shiftY) * tileSize - offy
        return screen_x, screen_y

    def _create_canvas_item(self, tx, ty, tz, tk_img):
        '''Create a canvas image item for tile (tx, ty, tz). Returns canvas item id.'''
        pos = self._tile_screen_pos(tx, ty)
        if pos is None:
            pos = (0, 0)
        return self.C.create_image(pos[0], pos[1], image=tk_img, anchor='nw')

    def _load_tile_bg(self, tx, ty, tz, ts, gen):
        '''Background thread: compose tile image, cache it, then schedule canvas creation.'''
        try:
            img = self.getTile(tx, ty, tz, ts)
        except Exception:
            return
        # Store in PIL cache — CPython GIL makes single dict writes atomic
        cache_key = (tx, ty, tz, ts)
        if len(self._pil_cache) >= MAX_PIL_CACHE:
            self._pil_cache.pop(next(iter(self._pil_cache)), None)
        self._pil_cache[cache_key] = img
        # Hand off to main thread for canvas operations
        self.C.after(0, lambda: self._apply_bg_tile(tx, ty, tz, img, gen))

    def _apply_bg_tile(self, tx, ty, tz, img, gen):
        '''Main thread callback: create canvas item for a background-loaded tile.'''
        if gen != self._refresh_gen:
            return   # stale generation, view has moved on
        key = (tx, ty, tz)
        if key not in self._required_keys:
            return   # tile no longer needed
        if key in self.tiles:
            return   # already created (two threads raced for same tile)

        tk_img = ImageTk.PhotoImage(img)
        self.bgImg[key] = tk_img
        item = self._create_canvas_item(tx, ty, tz, tk_img)
        self.tiles[key] = item
        self.C.lower(item)

        # If centerview, position it precisely (update() won't be called again immediately)
        if self.centerview:
            pos = self._tile_screen_pos(tx, ty)
            if pos is not None:
                try:
                    self.C.moveto(item, pos[0], pos[1])
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Core refresh / update
    # ------------------------------------------------------------------
    def refreshTiles(self, cx, cy, z):
        '''
        Reload map tiles for center tile (cx, cy) at zoom z.
        Reuses existing canvas tiles that are still in view; loads new ones
        (synchronously from PIL cache, or asynchronously from disk/network).
        '''
        ts = int(time.time())
        ts = ts - (ts % 300)   # 5 min granularity
        self._tile_ts = ts

        if self.enableClouds:
            self.wc.updateCloudUrl()

        tileSize = self.tileSize_
        tileNum = self.tileNum_
        shiftX = tileNum[0] // 2
        shiftY = tileNum[1] // 2
        inc = 0 if not self.centerview else 1

        # Compute the set of tile coordinates required for this view
        required: set = set()
        for j in range(tileNum[1] + inc):
            for i in range(tileNum[0] + inc):
                required.add((cx + i - shiftX, cy + j - shiftY, z))
        self._required_keys = required

        # If rendering config changed, invalidate PIL cache and drop all canvas tiles
        sig = self._cfg_signature()
        if self._cfg_sig != sig:
            self._pil_cache.clear()
            self._cfg_sig = sig
            for item in self.tiles.values():
                self.C.delete(item)
            self.tiles.clear()
            self.bgImg.clear()

        # Remove canvas tiles that have scrolled out of view
        stale = set(self.tiles.keys()) - required
        for key in stale:
            self.C.delete(self.tiles.pop(key))
            self.bgImg.pop(key, None)

        # Bump generation counter so any in-flight background loads for the old view are discarded
        self._refresh_gen += 1
        gen = self._refresh_gen

        # Load tiles not yet on canvas
        new_keys = required - set(self.tiles.keys())
        for tx, ty, tz in new_keys:
            cache_key = (tx, ty, tz, ts)
            if cache_key in self._pil_cache:
                # Fast path: already composited — create canvas item immediately
                tk_img = ImageTk.PhotoImage(self._pil_cache[cache_key])
                self.bgImg[(tx, ty, tz)] = tk_img
                item = self._create_canvas_item(tx, ty, tz, tk_img)
                self.tiles[(tx, ty, tz)] = item
            else:
                # Slow path: load in background thread
                threading.Thread(
                    target=self._load_tile_bg,
                    args=(tx, ty, tz, ts, gen),
                    daemon=True,
                ).start()

        # Lower all tile canvas items below flight icons
        for item in self.tiles.values():
            self.C.lower(item)

    def update(self, x, y, z, force=False):
        self.zoom_ = z
        tileSize = self.tileSize_
        tileNum = self.tileNum_

        if self.centerview:
            if tileNum[0] & 1 == 0:
                x_, offx = x // tileSize, x % tileSize
            else:
                x_, offx = (x - tileSize // 2) // tileSize, (x - tileSize // 2) % tileSize
            if tileNum[1] & 1 == 0:
                y_, offy = y // tileSize, y % tileSize
            else:
                y_, offy = (y - tileSize // 2) // tileSize, (y - tileSize // 2) % tileSize
        else:
            if tileNum[0] & 1 == 0:
                x_, offx = (x + tileSize // 2) // tileSize, (x + tileSize // 2) % tileSize
            else:
                x_, offx = x // tileSize, x % tileSize
            if tileNum[1] & 1 == 0:
                y_, offy = (y + tileSize // 2) // tileSize, (y + tileSize // 2) % tileSize
            else:
                y_, offy = y // tileSize, y % tileSize

        self.offset_ = (offx, offy)

        if self.center_ != (x_, y_) or force:
            self.center_ = (x_, y_)
            self.refreshTiles(x_, y_, z)

        if self.centerview:
            shiftX = tileNum[0] // 2
            shiftY = tileNum[1] // 2
            cx, cy = self.center_
            for (tx, ty, tz), item in list(self.tiles.items()):
                if tz != z:
                    continue
                screen_x = (tx - cx + shiftX) * tileSize - offx
                screen_y = (ty - cy + shiftY) * tileSize - offy
                self.C.moveto(item, screen_x, screen_y)

    def getPlanePos(self):
        '''
        Get the plane position as window coordinate

        @return the binary image data
        '''
        if self.centerview:
            sx = self.tileSize_ * self.tileNum_[0] / 2
            sy = self.tileSize_ * self.tileNum_[1] / 2
        else:
            sx = self.tileSize_ * self.tileNum_[0] // 2 + self.offset_[0]
            sy = self.tileSize_ * self.tileNum_[1] // 2 + self.offset_[1]
            sx -= self.tileSize_ // 2
            sy -= self.tileSize_ // 2
        return sx, sy
