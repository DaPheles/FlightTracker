from urllib import request
import datetime
import time
import math
import ephem

class IssAPI:
    def __init__(self):
        self.init_iss()

    def init_iss(self):
        # get Two-line element set of ISS (ZARYA) for position prediction
        url = "http://celestrak.org/NORAD/elements/stations.txt"
        response = request.urlopen(url).read().decode()
        # extract ISS data in first 3 lines
        tle = response.split("\n")[0:3]
        self.iss = ephem.readtle(tle[0], tle[1], tle[2])

    def get_position(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        #now = datetime.datetime.fromtimestamp(time.time()-2200)
        self.iss.compute(now)
        #print("elevation", self.iss.elevation)
        return int(now.timestamp()), math.degrees(self.iss.sublat), math.degrees(self.iss.sublong)

if __name__ == "__main__":
    # simple test
    iss = IssAPI()
    print(iss.get_position())
