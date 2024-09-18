'''
    helper class to handle airplane trails from FlightRadar24 histories or current locations
'''

import json
import time
from FlightRadar24_patch.api import FlightRadar24API
from coords import *
from tiles import Tiles
from helper import Dict2Class

class Trails(object):
    def __init__(self, fr_api:FlightRadar24API, flight, tiles:Tiles, maxTrail=200, centerview=True):
        self.fr_api = fr_api
        self.flight = flight
        self.f = Dict2Class(dict(id=self.flight))
        self.tiles = tiles
        self.maxTrail = maxTrail
        self.centerview = centerview

        self.trail = self.getFlightHistory()
        #self.trail = list()
        self.trailHQ = len(self.trail)
        self.updateTS = -1
        self.updateTick = 0
    
    def setUpdateTick(self, tick):
        self.updateTick = tick

    def getFlightHistory(self, saveHistory=False):
        ''' get initial flight trace from flight history prior now
        '''
        trail = list()
        details = self.fr_api.get_flight_details(self.f)

        # print first timestamp
        if isinstance(details, dict):
            if 'firstTimestamp' in details:
                ts_first = details['firstTimestamp']
                ts_ = time.strftime("%H:%M:%S", time.localtime(ts_first))

            if 'trail' in details:
                l = len(details["trail"])
                if l > 0:
                    if saveHistory:
                        with open(f'{self.flight}_aircraft.json', 'w') as fp:
                            json.dump(details['aircraft'], fp,
                                    sort_keys=True, indent=2)
                        with open(f'{self.flight}_history.json', 'w') as fp:
                            json.dump(details, fp, sort_keys=True, indent=2)
                        f = open(f"{self.flight}.csv", "w")
                        f.write("ts,lat,lng,alt,spd,hd\n")

                    for i in range(l-1, 0, -1):
                        ts = details['trail'][i]['ts']
                        lat = details['trail'][i]['lat']
                        lng = details['trail'][i]['lng']
                        trail.append((ts, lat, lng))
                        if saveHistory:
                            ts = details['trail'][i]['ts']
                            alt = details['trail'][i]['alt']
                            spd = details['trail'][i]['spd']
                            hd = details['trail'][i]['hd']
                            f.write(f"{ts},{lat},{lng},{alt},{spd},{hd}\n")
                    if saveHistory:
                        f.close()
        
        if len(trail) > self.maxTrail:
            del trail[:len(trail)-self.maxTrail]

        return trail

    def new(self, step):
        self.trail.append(step)
        # forget the past
        if len(self.trail) > self.maxTrail:
          del self.trail[0]
          self.trailHQ -= 1

    def update(self, details=dict()):
        # get full flight history on first update() call
        if self.updateTS < 0:
            #self.trail = self.fr_api.get_flight_details(self.flight)
            try:
                self.trail = self.getFlightHistory()
            except:
                return list()
            self.trailHQ = len(self.trail)
            self.updateTS = time.time()
        elif len(details) == 0:
            try:
                details = self.fr_api.get_flight_details(self.f)
            except:
                # do nothing
                return list()

        # trail optimisation: remove high frequency low quality locations and
        # replace then by history data with minimized frequency and high quality locations
        if time.time() > self.updateTS+self.updateTick and self.trailHQ > 0 and 'trail' in details:
            hq_ts = self.trail[self.trailHQ-1][0]
            hq_last_ts = 0
            newlist = list()
            if details["trail"]:
                for det in details["trail"]:
                    if det['ts'] > hq_ts:
                        if hq_last_ts < det['ts']:
                            hq_last_ts = det['ts']
                        newlist.append((det['ts'], det['lat'], det['lng'], det['alt']))

            # get list of bad locations
            badlist = list()
            for i, t in enumerate(self.trail[self.trailHQ:]):
                if t[0] <= hq_last_ts:
                    badlist.append(self.trailHQ+i)

            # first action: remove obsolete data
            if len(badlist) > 0:
                del self.trail[badlist[0]:badlist[-1]+1]

            # second: insert newlist if available
            if len(newlist) > 0:
                self.trail.extend(newlist)
                self.trail.sort()
                self.trailHQ += len(newlist)

        # draw flight trail
        trail_ = list()
        tileSize = self.tiles.tileSize
        tileNum  = self.tiles.tileNum
        z = self.tiles.zoom
        for step in reversed(self.trail):
            #tx, ty = worldToPixel(lngToXWorld(step[2]), latToYWorld(step[1]), z)
            tx, ty = latlngToPixel(step[1:3], z)
            tilex, tiley = tx//tileSize, ty//tileSize
            if abs(self.tiles.center[0]-tilex) > tileNum[0] or \
               abs(self.tiles.center[1]-tiley) > tileNum[1]:
                #print(self.tiles.center[0], tilex, "|", self.tiles.center[1], tiley)
                break
            if self.centerview:
                tx_ = tileSize * (tilex-self.tiles.center[0]+tileNum[0]//2) + (tx % tileSize) - self.tiles.offset[0]
                ty_ = tileSize * (tiley-self.tiles.center[1]+tileNum[1]//2) + (ty % tileSize) - self.tiles.offset[1]
            else:
                tx_ = tileSize * (tilex-self.tiles.center[0]+tileNum[0]//2) + (tx % tileSize)
                ty_ = tileSize * (tiley-self.tiles.center[1]+tileNum[1]//2) + (ty % tileSize)
            trail_ += [tx_, ty_]
        
        self.updateTS = int(time.time())
        
        return trail_
