'''
    helper class to handle Wetter.com weather radar images
'''

import requests
import time, os, json
from PIL import Image

class WetterComAPI:
    def __init__(self):
        self.ts = -1
        self.datetime = time.strftime("%Y%m%d%H", time.gmtime(time.time())) + '00'
        self.tile = None
        self.localeLang = 'en'
        self.localeCountry = 'GB'
        self.cloudUrl = None
        self.cloudTs = 0
        self.cachePath = os.path.join("cache", "wetter.com")

    def setLocale(self, lang, country):
        self.localeLang = lang
        self.localeCountry = country

    def getRadarImage(self, x, y, z, ts=None):
        if not ts:
            # snap timestamp into 5min granularity
            ts=int(time.time())
            ts=ts-(ts%300)
        now = time.strftime("%Y%m%d%H%M", time.gmtime(ts))
        x_,y_,z_ = x//2, y//2, z-1
        if self.tile:
            url = f"https://d3q1in6xcpf6ou.cloudfront.net/{self.tile}/{z_}/{x_}/{y_}"
        else:
            url = f"https://d3q1in6xcpf6ou.cloudfront.net/nearcast/composite_ng_snow/{self.datetime}/{now}/{z_}/{x_}/{y_}"
        
        filename = f"radar_{ts},{z_},{x_},{y_}.dat"

        # check for subfolders and create them if needed
        if not os.path.exists(self.cachePath):
            os.makedirs(self.cachePath)

        filename = os.path.join(self.cachePath, filename)
        if os.path.exists(filename):
            # load existing file and return image
            img = Image.open(filename, formats=['jpeg', 'png']).convert("RGBA")
            return img

        # get radar image
        headers = {
            "host": "d3q1in6xcpf6ou.cloudfront.net",
            "user-agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/112.0",
            "accept": "*/*",
            "accept-language": f"{self.localeLang}-{self.localeCountry};q=0.7,en;q=0.3",
            "accept-encoding": "gzip, deflate, br",
            "connection": "keep-alive",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "pragma": "no-cache",
            "cache-control": "no-cache"
        }

        req = requests.get(url, allow_redirects=True, headers=headers)
        if req.status_code == 200:
            # on success: save image to file system and load as RGBA image
            data = req.content
            with open(filename, "wb") as f:
                f.write(data)
            img = Image.open(filename, formats=['jpeg', 'png']).convert("RGBA")
        else:
            img = None

        return img

    def getRadarStatus(self):
        headers = {
            "host": "d3q1in6xcpf6ou.cloudfront.net",
            "accept": "*/*",
            "accept-language": f"{self.localeLang}-{self.localeCountry};q=0.7,en;q=0.3",
            "accept-encoding": "gzip,deflate,br",
            "connection": "keep-alive",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "pragma": "no-cache",
            "cache-control": "no-cache"
        }
        url = "https://d3q1in6xcpf6ou.cloudfront.net/status/radar/composite_snow/status.json"
        req = requests.get(url, allow_redirects=True, headers=headers)
        if req.status_code != 200:
            # no success!
            print(f"WetterComAPI::getRadarStatus(): Request Error: {req.status_code}")
            return None
        response = req.content
        # try to decode content
        if isinstance(response, (bytes, bytearray)):
            try:
                response = json.loads(response.decode('utf-8'))
            except:
                print(f"WetterComAPI::getRadarStatus(): Could not decode response!")
                response = dict()
        return response
    
    def setRadarTimestamp(self, ts):
        found = False
        if self.ts != ts:
            cfg = self.getRadarStatus()
            #print(cfg)
            if cfg is not None and 'timesteps' in cfg:
                # find latest real radar datetime stamp
                for step in cfg['timesteps']:
                    #datetime = time.strftime("%Y%m%d%H%M", time.gmtime(ts))
                    #print(datetime, step)
                    dt = -1
                    if step['tiles'][:5] == "radar":
                        found = True
                        if dt < int(step['tiles'][-12:]):
                            self.datetime = step['tiles'][-12:]
                            self.tile = step['tiles']
                            dt = int(self.datetime)
            if found:
                self.ts = ts
        return found

    def updateCloudUrl(self):
        url = "https://www.wetter.com/agt/wetterkarten/tiles/icon_clouds/minimal"
        headers = {
            "host": "www.wetter.com",
            "accept": "application/json, text/plain, */*",
            "accept-language": f"{self.localeLang}-{self.localeCountry};q=0.7,en;q=0.3",
            "accept-encoding": "gzip, deflate, br",
            "connection": "keep-alive",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "pragma": "no-cache",
            "cache-control": "no-cache",
        }
        req = requests.get(url, allow_redirects=True, headers=headers)
        if req.status_code != 200:
            # no success!
            print("Error (WetterComAPI::updateCloudUrl): Error on request of Cloud URL!")
            return None
        response = req.content

        # try to decode content
        if isinstance(response, (bytes, bytearray)):
            try:
                response = json.loads(response.decode('utf-8'))
            except:
                response = dict()
        
        ts = int(time.time())
        ts -= ts%3600

        now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))+"+00:00"
        try:
            for step in response['runs'][0]['timesteps']:
                if step['date'] == now:
                    self.cloudUrl = "https://ct3.wettercomassets.com/" + step['tile_url']
                    self.cloudTs = ts
                    break
        except:
            self.cloudUrl = None
    
    def getCloudImage(self, x, y, z):
        if not self.cloudUrl:
            print("Error: Cloud URL not updated!")
            return None

        url = self.cloudUrl.format(z=z,x=x,y=y)
        filename = f"clouds_{self.cloudTs},{z},{x},{y}.dat"

        # check for subfolders and create them if needed
        if not os.path.exists(self.cachePath):
            os.makedirs(self.cachePath)

        filename = os.path.join(self.cachePath, filename)
        if os.path.exists(filename):
            # load existing file and return image
            img = Image.open(filename, formats=['jpeg', 'png']).convert("RGBA")
            return img

        headers = {
            "host": "ct3.wettercomassets.com",
            "user-agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/112.0",
            "accept": "image/png",
            "accept-language": f"{self.localeLang}-{self.localeCountry};q=0.7,en;q=0.3",
            "accept-encoding": "gzip,deflate,br",
        }
        req = requests.get(url, allow_redirects=True, headers=headers)
        if req.status_code == 200:
            # on success: save image to file system and load as RGBA image
            data = req.content
            with open(filename, "wb") as f:
                f.write(data)
            img = Image.open(filename, formats=['jpeg', 'png']).convert("RGBA")
        else:
            print("Error (WetterComAPI::getCloudImage): req.status_code:", req.status_code)
            img = None
        return img

if __name__ == "__main__":
    # simple test
    ts=int(time.time())
    ts=ts-(ts%300)  # 5 min granularity

    wc = WetterComAPI()
    wc.updateCloudUrl()
    print(wc.cloudUrl)
