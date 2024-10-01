from urllib import request
import datetime, time
import math
import json

class SkyawareAPI:
    def __init__(self):
        #self.url = "http://localhost/skyaware/data/aircraft.json"
        self.url = "http://localhost/dump1090/data/aircraft.json"
        self.flights = dict()

    def get_flights(self, icao=None):
        if icao:
            if icao in self.flights:
                return self.flights[icao]
            else:
                return None
        return self.flights

    def update(self):
        try:
            response = json.loads(request.urlopen(self.url).read().decode())
        except Exception as e:
            #raise Exception(e)
            return
        
        ts = response['now']
        for ac in response['aircraft']:
            hex = ac["hex"].upper()
            if hex not in self.flights:
                flight = dict()
            else:
                flight = self.flights[hex]

            if 'flight' in ac:
                flight['callsign'] = ac['flight'].strip()
            if 'lat' in ac:
                flight['lat'] = ac['lat']
            if 'lon' in ac:
                flight['lng'] = ac['lon']
            if 'alt_baro' in ac:
                flight['alt'] = ac['alt_baro']
            if 'nav_heading' in ac:
                flight['heading'] = ac['nav_heading']
            if 'rssi' in ac:
                flight['rssi'] = ac['rssi']
            flight['time'] = float(ts)
            if 'seen' in ac:
                flight['time'] -= ac['seen']

            if hex not in self.flights:
                self.flights[hex] = flight

        #print(len(response['aircraft']), len(self.flights), self.flights[list(self.flights.keys())[0]])

if __name__ == "__main__":
    # simple test
    sa = SkyawareAPI()
    while(True):
        sa.update()
        time.sleep(1)
