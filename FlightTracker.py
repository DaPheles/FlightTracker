#!/usr/bin/python
'''
    Application to show local FlightRadar using FlightRadar24 API and Google Maps tiles
'''

from python.flightTracker import FlightTracker

if __name__ == "__main__":
  # create Application
  ft = FlightTracker()
  ft.mainloop()
