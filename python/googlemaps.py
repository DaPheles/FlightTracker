'''
    helper class to handle Google Maps tiles
'''

from pathlib import Path
import requests
from PIL import Image
from logger import get_logger

logger = get_logger(__name__)

MAX_RAW_CACHE = 256   # raw (unprocessed) tile images kept in memory


class GoogleMapsAPI(object):
    def __init__(self):
        self.cachePath = Path(".cache") / "tiles"
        self.localeLang = 'en'
        self.localeCountry = 'GB'
        # in-memory raw tile cache: (x, y, z, style) -> PIL Image (RGBA, unmodified)
        self._raw_cache: dict = {}

    def setLocale(self, lang, country):
        self.localeLang = lang
        self.localeCountry = country

    def getTileImage(self, x, y, z, tileSize, style, debug=False):
        # check in-memory raw cache first (avoids disk I/O when tile was recently loaded)
        raw_key = (x, y, z, style)
        if raw_key in self._raw_cache:
            return self._raw_cache[raw_key].copy()

        tile_dir = self.cachePath / style / str(z)

        # check for subfolders and create them if not available
        tile_dir.mkdir(parents=True, exist_ok=True)

        filepath = tile_dir / f"{x},{y}.dat"
        if not filepath.exists():
            headers = {
                "accept": "image/avif,image/webp,*/*",
                "accept-encoding": "gzip, br",
                "accept-language": f"{self.localeLang}-{self.localeCountry},en-US;q=0.7,en;q=0.3",
                "user-agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0"
            }

            # get missing tile from google maps
            if style == "satellite":
                url = f"https://maps.googleapis.com/maps/vt/lyrs=s?x={x}&y={y}&z={z}&scale=1"
            elif style == "terrain":
                url = f"https://maps.google.com/maps/vt/pb=!1m5!1m4!1i{z}!2i{x}!3i{y}!4i{tileSize}!2m2!1e5!2sshading!2m2!1e6!2scontours!2m3!1e0!2sm!3i768532399!3m7!2s{self.localeLang}!5e1105!12m4!1e68!2m2!1sset!2sTerrain!4e0"
            else:
                # style == "roadmap"
                url = f"https://maps.google.com/maps/vt?pb=!1m5!1m4!1i{z}!2i{x}!3i{y}!4i{tileSize}!2m3!1e0!2sm!3i643381729!3m17!2s{self.localeLang}!3s{self.localeCountry}!5e18!12m4!1e68!2m2!1sset!2sRoadmapSatellite!12m3!1e37!2m1!1ssmartmaps!12m4!1e26!2m2!1sstyles!2zcy50OjMzfHMuZTpsfHAudjpvZmY!4e0!23i1379903"

            # try to download image
            req = requests.get(url, allow_redirects=True, headers=headers)
            if req.status_code == 200:
                logger.debug(f"Downloaded '{style}' tile: {url}")
                # on success: save image to file system and load as RGBA image
                data = req.content
                with open(filepath, "wb") as f:
                    f.write(data)
                img = Image.open(filepath, formats=["jpeg","png"]).convert("RGBA")
            else:
                logger.warning(f"Error downloading '{style}' tile: Status={req.status_code} ({url})")
                # image data not successfully downloaded, use pink image by default
                img = Image.new(mode="RGBA", size=(tileSize, tileSize), color="pink")
        else:
            # if filename exists: load as RGBA image
            img = Image.open(filepath, formats=["jpeg","png"]).convert("RGBA")

        # store in raw cache (copy so callers can freely mutate the returned image)
        if len(self._raw_cache) >= MAX_RAW_CACHE:
            self._raw_cache.pop(next(iter(self._raw_cache)), None)
        self._raw_cache[raw_key] = img.copy()

        return img
