'''
    helper class to handle Google Maps tiles
'''

import os
import requests
from PIL import Image

class GoogleMapsAPI(object):
    def __init__(self):
        self.cachePath = os.path.join("cache", "tiles")
        self.localeLang = 'en'
        self.localeCountry = 'GB'
        self.server = 0

    def setLocale(self, lang, country):
        self.localeLang = lang
        self.localeCountry = country

    def getTileImage(self, x, y, z, tileSize, style, debug=False):
        dirname = os.path.join(self.cachePath, style, str(z))

        # check for subfolders and create them if not available
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        filename = os.path.join(dirname, f"{x},{y}.dat")
        if not os.path.exists(filename):
            headers = {
                "accept": "image/avif,image/webp,*/*",
                "accept-encoding": "gzip, br",
                "accept-language": f"{self.localeLang}-{self.localeCountry},en-US;q=0.7,en;q=0.3",
                "user-agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
            }

            # get missing tile from google maps
            if style == "satellite":
                #headers = {
                #    "accept": "image/avif,image/webp,*/*",
                #    "accept-encoding": "gzip, br",
                #    "accept-language": f"{self.localeLang}-{self.localeCountry};q=0.7,en;q=0.3",
                #    "cache-control": "no-cache",
                #    "connection": "keep-alive",
                #    "host": f"khms{self.server}.googleapis.com",
                #    "alt-used": f"khms{self.server}.googleapis.com",
                #    "sec-fetch-dest": "image",
                #    "sec-fetch-mode": "no-cors",
                #    "sec-fetch-site": "cross-site",
                #    "pragma": "no-cache",
                #    "upgrade-insecure-requests": "1"
                #}
                #v = 988     # API version, may be incremented from time to time
                v = 946     # API version, may be incremented from time to time
                headers = {
                    "accept": "image/avif,image/webp,*/*",
                    "accept-encoding": "gzip, br",
                    "accept-language": f"{self.localeLang}-{self.localeCountry},en-US;q=0.7,en;q=0.3",
                    "cache-control": "no-cache",
                    "connection": "keep-alive",
                    "host": f"khms{self.server}.googleapis.com",
                    "alt-used": f"khms{self.server}.googleapis.com",
                    "sec-fetch-dest": "image",
                    "sec-fetch-mode": "no-cors",
                    "sec-fetch-site": "cross-site",
                    "pragma": "no-cache",
                    "te": "trailers",
                    "upgrade-insecure-requests": "1",
                    "user-agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
                }
                url = f"https://khms{self.server}.googleapis.com/kh?v={v}&hl=en&x={x}&y={y}&z={z}"
                self.server = 1 - self.server   # toggle 0-1-0-1
            elif style == "terrain":
                url = f"https://maps.google.com/maps/vt?pb=!1m5!1m4!1i{z}!2i{x}!3i{y}!4i{tileSize}!2m3!1e4!2st!3i639!2m3!1e0!2sr!3i639377937!3m17!2s{self.localeLang}!3s{self.localeCountry}!5e18!12m4!1e8!2m2!1sset!2sTerrain!12m3!1e37!2m1!1ssmartmaps!12m4!1e26!2m2!1sstyles!2zcy50OjMzfHMuZTpsfHAudjpvZmY!4e0!23i1379903"
            else:
                # style == "roadmap"
                url = f"https://maps.google.com/maps/vt?pb=!1m5!1m4!1i{z}!2i{x}!3i{y}!4i{tileSize}!2m3!1e0!2sm!3i643381729!3m17!2s{self.localeLang}!3s{self.localeCountry}!5e18!12m4!1e68!2m2!1sset!2sRoadmapSatellite!12m3!1e37!2m1!1ssmartmaps!12m4!1e26!2m2!1sstyles!2zcy50OjMzfHMuZTpsfHAudjpvZmY!4e0!23i1379903"

            # try to download image
            req = requests.get(url, allow_redirects=True, headers=headers)
            if req.status_code == 200:
                if debug: print(f"Downloading success of '{style}' tile ({url})!")
                print(f"Downloading success of '{style}' tile ({url})!")
                # on success: save image to file system and load as RGBA image
                data = req.content
                with open(filename, "wb") as f:
                    f.write(data)
                img = Image.open(filename, formats=["jpeg","png"]).convert("RGBA")
            else:
                if debug: print(f"Error downloading '{style}' tile: Status={req.status_code} ({url})")
                print(f"Error downloading '{style}' tile: Status={req.status_code} ({url})")
                # image data not successfully downloaded, use pink image by default
                img = Image.new(mode="RGBA", size=(tileSize, tileSize), color="pink")
        else:
            # if filename exists: load as RGBA image
            img = Image.open(filename, formats=["jpeg","png"]).convert("RGBA")

        return img
