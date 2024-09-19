'''
    helper class to handle airplane sprites
    get and use FlightRadar24 resources
'''

import json
import os
import requests
from PIL import Image, ImageTk

class Sprites:
    def __init__(self, sprites=[25,30,35,80]):
        self.sprites = sprites
        self.spritesR = dict()
        self.spritesY = dict()
        self.spritesB = dict()
        self.sprite_cfg = dict()
        self.cachePath = os.path.join("cache", "sprites")
        self.downloadResources()
        self.loadSprites()  # possible: 25,30,35,80
        self.planeImage = None

    def downloadResources(self):
        #cachePath = os.path.join(os.path.dirname(__file__), "sprites")
        if not os.path.exists(self.cachePath):
            os.makedirs(self.cachePath)
        
        # get selection of sprites config
        for size in self.sprites:
            for color in ["yellow", "red", "blue"]:
                spriteCfgFilename = os.path.join(self.cachePath, f"sprite_{size}_{color}.json")
                spriteIconFilename = os.path.join(self.cachePath, f"sprite_{size}_{color}.dat")

                if not os.path.exists(spriteCfgFilename):
                    url = f"https://www.flightradar24.com/aircraft-icons/sprite?size={size}&scale=1&color={color}&shadow=yes"
                    req = requests.get(url)
                    if req.status_code == 200:
                        response = req.content

                        # try to decode content
                        if isinstance(response, (bytes, bytearray)):
                            try:
                                response = json.loads(response.decode('utf-8'))
                            except:
                                response = dict()

                        # safe to sprites config json
                        with open(spriteCfgFilename, "w") as f:
                            f.write(json.dumps(response))
                    else:
                        print(f"Error (Sprites::downloadResources)! Unable to download resource {url}!")
        
                if not os.path.exists(spriteIconFilename):
                    with open(spriteCfgFilename, "r") as f:
                        cfg = json.loads(f.read())
                        if 'url' in cfg:
                            url = f"https://images.flightradar24.com/assets/aircraft/cached/{cfg['url']}"
                            headers = {
                                "accept": "image/avif,image/webp,*/*",
                                "accept-language": "en-US;q=0.7,en;q=0.3",
                                "accept-encoding": "gzip, deflate, br",
                                "sec-fetch-dest": "image",
                                "sec-fetch-mode": "no-cors",
                                "sec-fetch-site": "same-site",
                                "pragma": "no-cache",
                                "cache-control": "no-cache",
                            }
                            req = requests.get(url, headers=headers)
                            if req.status_code == 200:
                                response = req.content

                                # safe to sprites image
                                with open(spriteIconFilename, "wb") as f:
                                    f.write(response)
                            else:
                                print(f"Error! Unable to download resource {url}!")
        
    def loadSprites(self):
        for size in self.sprites:
            self.spritesR[size] = Image.open(os.path.join(self.cachePath, f"sprite_{size}_red.dat"), formats=['png']).convert("RGBA")
            self.spritesY[size] = Image.open(os.path.join(self.cachePath, f"sprite_{size}_yellow.dat"), formats=['png']).convert("RGBA")
            self.spritesB[size] = Image.open(os.path.join(self.cachePath, f"sprite_{size}_blue.dat"), formats=['png']).convert("RGBA")
            with open(os.path.join(self.cachePath, f"sprite_{size}_yellow.json")) as f:
                self.sprite_cfg[size] = json.load(f)
        return

    def getIcon(self, flight, size, col):
        '''
        Retrieve proper aircraft icon according to flight attributes. Needs correct sprites map already loaded.
        
        @param flight the flight object
        @param size the requested icon magnification
        @param col the color of the aircraft ('R', 'B', or 'Y')
        
        @return the ImageTK PhotoImage of the icon
        '''
        # find proper aircraft
        cfg_ = None
        if flight.aircraft_code in self.sprite_cfg[size]['icons']:
            cfg_ = self.sprite_cfg[size]['icons'][flight.aircraft_code]
        else:
            for aircraft in self.sprite_cfg[size]['icons']:
                if flight.aircraft_code in self.sprite_cfg[size]['icons'][aircraft]['aliases']:
                    cfg_ = self.sprite_cfg[size]['icons'][aircraft]
                    break
        if cfg_ is None:
            #print(f"Yiiiiaiks! Aircraft code not in sprite config ({flight.aircraft_code})")
            # use default 
            aircraft_code = "C206"
            if aircraft_code in self.sprite_cfg[size]['icons']:
                cfg_ = self.sprite_cfg[size]['icons'][aircraft_code]
            else:
                for aircraft in self.sprite_cfg[size]['icons']:
                    if aircraft_code in self.sprite_cfg[size]['icons'][aircraft]['aliases']:
                        cfg_ = self.sprite_cfg[size]['icons'][aircraft]
                        break
            if cfg_ is None:
                return None
        
        # get heading index
        idx = 0
        if cfg_['rotates']:
            idx = (round(flight.heading/self.sprite_cfg[size]['rotationDegrees'])*self.sprite_cfg[size]['rotationDegrees']) % 360
        coords = cfg_['frames'][0][str(idx)]
        x,y,w,h_ = coords['x'],coords['y'],coords['w'],coords['h']
        # workaround: parameter h is wrong in json file, try to fix it by using parameter w at 90 degrees rotation
        h = cfg_['frames'][0][str((idx+90)%360)]['w']
    
        sprites = self.spritesR if col == 'R' else self.spritesB if col == 'B' else self.spritesY
        self.planeImage = ImageTk.PhotoImage(sprites[size].crop((x,y,x+w,y+h)))
        return self.planeImage
