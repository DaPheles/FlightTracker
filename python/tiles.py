'''
    handle map tiles
'''

import os, time
from PIL import Image, ImageTk
from coords import *
from wettercom import WetterComAPI
from googlemaps import GoogleMapsAPI
import numpy as np

CLOUDS_ALPHA = 0.6
DEBUG = False

class Tiles(object):
    def __init__(self, canvas, tileSize:int, tileNum, style:dict, zoom, home, centerview=True):
        self.C = canvas
        self.tileSize_ = tileSize
        self.tileNum_ = tileNum
        self.style = style
        self.bgImg = dict()
        self.tiles = dict()
        self.zoom_ = zoom
        self.centerview = centerview

        self.homeX_,self.homeY_ = latlngToPixel(home, zoom)
        self.center_ = None
        self.offset_ = None
        self.homeRadarIndex_ = 0

        self.localeLang = 'en'      # English per default
        self.localeCountry = 'GB'   # GreatBritain per default
        self.enableClouds = False   # disabled by default
        self.enableRadar  = False   # disabled by default

        # bind Wetter.com API for optional rain/cloud overlays
        self.wc = WetterComAPI()
        self.gm = GoogleMapsAPI()

        self.focus_ = None
        if centerview:
            # set HOME focus
            sx = tileNum[0]*tileSize/2
            sy = tileNum[1]*tileSize/2
            self.focus_ = self.C.create_oval([sx-5,sy-5,sx+5,sy+5], fill='#FFAA66', tags='home', width=2)

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

    def toggleClouds(self):
        self.enableClouds = not self.enableClouds

    def toggleRadar(self):
        self.enableRadar = not self.enableRadar

    @property
    def homeRadarIndex(self):
        return self.homeRadarIndex_
    
    def setLocale(self, lang, country):
        self.localeLang = lang
        self.localeCountry = country
        if self.wc:
            self.wc.setLocale(lang, country)
        if self.gm:
            self.gm.setLocale(lang, country)
    
    def getTile(self, x, y, z, ts=None):
        '''
        Downloads a map tile image and store in tile cache. If already available, load the stored image.

        @param x the x value of the world coordinate
        @param y the y value of the world coordinate
        @param z the zoom level of the world coordinate

        @return the binary image data
        '''

        img = self.gm.getTileImage(x, y, z, self.tileSize_, self.style['basemap'], debug=DEBUG)
        if self.style['roadmap']:
            img_overlay = self.gm.getTileImage(x, y, z, self.tileSize_, 'roadmap', debug=DEBUG)
            img.paste(img_overlay, (0, 0), img_overlay)

        # brightness adjust
        img_ = np.array(img)
        img_[:,:,:3] = (img_[:,:,:3]*self.style['brightness']).astype(np.uint8)
        img = Image.fromarray(img_)
        
        # render cloud radar overlay with zoom levels smaller or equal 13 only
        if self.enableClouds and z <= 13:
            if DEBUG: print(f"Tiles::getTile(): Trying to get cloud image for x={x}, y={y}, z={z}")
            img_overlay = self.wc.getCloudImage(x, y, z)
            if img_overlay:
                img_overlay_ = np.array(img_overlay).astype(np.float32)
                img_overlay_[:,:,3] -= img_overlay_[:,:,3]*(1-CLOUDS_ALPHA)
                img_overlay = Image.fromarray(img_overlay_.astype(np.uint8))

                img = Image.fromarray(img_)
                img.paste(img_overlay, (0, 0), img_overlay)
                img_ = np.array(img)

        # render rain radar overlay with zoom levels smaller or equal 13 only
        if self.enableRadar and z <= 13:
            if ts == None:
                ts_ = int(time.time())
            else:
                ts_ = ts
            ts_ = ts_-(ts_%300)  # 5 min granularity

            self.wc.setRadarTimestamp(ts_)

            if DEBUG: print(f"Tiles::getTile(): Trying to get radar image for x={x}, y={y}, z={z}, ts={ts_}")
            img_overlay = self.wc.getRadarImage(x, y, z, ts_)
            if img_overlay:
                # returned image is 512x512, needs further subtiling!
                tilex, tiley = 256*(x%2), 256*(y%2)
                
                # TODO: make it nicer with ALPHA blending
                img_overlay = img_overlay.crop((tilex, tiley, tilex+256, tiley+256))
                img_overlay_ = np.array(img_overlay).astype(np.uint16)

                # get radar index of home location
                if x == self.homeX_//256 and y == self.homeY_//256:
                    self.homeRadarIndex_ = img_overlay_[self.homeY_%256, self.homeX_%256, 2]  # blue channel of HOME pixel
                
                img_[:,:,0] = np.clip(img_[:,:,0].astype(np.int16) -
                                    img_overlay_[:,:,2],0,255).astype(np.uint8)
                img_[:,:,1] = np.clip(img_[:,:,1].astype(np.int16) - 
                                    img_overlay_[:,:,2],0,255).astype(np.uint8)
                img_[:,:,2] = np.clip(img_[:,:,2].astype(np.int16) + 
                                    img_overlay_[:,:,2]*4,0,255).astype(np.uint8)
                img = Image.fromarray(img_)

        return img

    def refreshTiles(self, x, y, z):
        # clean-up
        for k in self.bgImg.keys():
            self.C.delete(self.bgImg[k])
            self.C.delete(self.tiles[k])

        # get current timestamp for all tiles
        ts = int(time.time())
        ts = ts-(ts%300)  # 5 min granularity

        # reload canvas tiles
        if self.enableClouds:
            self.wc.updateCloudUrl()

        tileSize = self.tileSize_
        tileNum = self.tileNum_
        shiftX = tileNum[0]//2
        shiftY = tileNum[1]//2
        inc = 0 if not self.centerview else 1
        for j in range(tileNum[1]+inc):
            for i in range(tileNum[0]+inc):
                image = ImageTk.PhotoImage(self.getTile(x+i-shiftX, y+j-shiftY, z, ts))
                self.bgImg[f'{j}{i}'] = image
                self.tiles[f'{j}{i}'] = self.C.create_image(tileSize*(i+0.5), tileSize*(j+0.5), image=image)

        for k in self.bgImg.keys():
            self.C.lower(self.bgImg[k])
            self.C.lower(self.tiles[k])

    def update(self, x, y, z, force=False):
        self.zoom_ = z
        tileSize = self.tileSize_
        tileNum = self.tileNum_
        if self.centerview:
            # airplane is always in the center of the window, map tile move
            if tileNum[0]&1 == 0:
                x_, offx = x//tileSize, x%tileSize
            else:
                x_, offx = (x-tileSize//2)//tileSize, (x-tileSize//2)%tileSize
            if tileNum[1]&1 == 0:
                y_, offy = y//tileSize, y%tileSize
            else:
                y_, offy = (y-tileSize//2)//tileSize, (y-tileSize//2)%tileSize
        else:
            # airplane moves inside the inner static maps tile
            if tileNum[0]&1 == 0:
                x_, offx = (x+tileSize//2)//tileSize, (x+tileSize//2)%tileSize
            else:
                x_, offx = x//tileSize, x%tileSize
            if tileNum[1]&1 == 0:
                y_, offy = (y+tileSize//2)//tileSize, (y+tileSize//2)%tileSize
            else:
                y_, offy = y//tileSize, y%tileSize
        
        self.offset_ = (offx, offy)

        if self.center_ != (x_,y_) or force:
            self.center_ = (x_,y_)
            self.refreshTiles(x_,y_,z)

        if self.centerview:
            for y in range(tileNum[1]+1):
                for x in range(tileNum[0]+1):
                    x_ = tileSize*x-offx
                    y_ = tileSize*y-offy
                    self.C.moveto(self.tiles[f'{y}{x}'], x_, y_)

    def getPlanePos(self):
        '''
        Get the plane position as window coordinate

        @return the binary image data
        '''
        if self.centerview:
            sx = self.tileSize_*self.tileNum_[0]/2
            sy = self.tileSize_*self.tileNum_[1]/2
        else:
            sx = self.tileSize_*self.tileNum_[0]//2 + self.offset_[0]
            sy = self.tileSize_*self.tileNum_[1]//2 + self.offset_[1]
            sx -= self.tileSize_//2
            sy -= self.tileSize_//2
        return sx,sy
