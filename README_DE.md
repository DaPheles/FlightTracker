# FlightTracker

Flight Tracker wurde für Bildungszwecke entwickelt und ist eines der ersten evolutionären Tools, das eine Reihe von Online-Diensten an einem Ort verfolgt und kombiniert.

Das Tool wurde entwickelt, um den Flugverkehr in der Umgebung zu visualisieren und Informationen über die Flugobjekte zu erhalten. Zusätzlich werden optionale aktuelle Wetterkarten angezeigt.

![flighttracker](images/flighttracker.png)

Derzeit enthaltene Dienste sind:
- [FlightRadar24](https://www.flightradar24.com) durch die inoffizielle [FlightRadarAPI](https://github.com/JeanExtreme002/FlightRadarAPI). Bitte beachten Sie die [Allgemeinen Geschäftsbedingungen](https://www.flightradar24.com/terms-and-conditions)!
- [Google Maps](https://www.google.com/maps) durch generierte API-lose Anfragen. Bitte beachten Sie die [Nutzungsbedingungen der Google Maps Platform](https://cloud.google.com/maps-platform/terms) und [Zusätzlichen Nutzungsbedingungen von Google Maps/Google Earth](https://www.google.com/intl/de_DE/help/terms_maps/)!
- [wetter.com](https://www.wetter.com/) Regen- und Wolkenradarkarten durch generierte API-lose Anfragen. Bitte beachten Sie die [Allgemeinen Geschäftsbedingungen](https://www.wetter.com/agb/)! (Service nur in Europa und Nordamerika verfügbar.)

## Installation

Laden Sie zum schnellen Test die Windows-Binärdatei als [FlightTracker.zip](https://pheles.de/FlightTracker.zip) herunter.

Der Flight Tracker ist eine Python-Anwendung. Alle aktuellen Python3-Versionen sollten problemlos laufen. Um ihn auf Ihrem Computer zu installieren, müssen Sie nur Folgendes tun:

```
git clone https://github.com/DaPheles/FlightTracker.git <install_path>
```

Wenn die Installation abgeschlossen ist, wechseln Sie in Ihren Installationspfad.

Installation von benötigten Abhängigkeiten:

```
pip install -r requirements.txt
```

Ausführen von FlightTracker:

```
python FlightTracker.py
```

## Konfiguration

Die Konfigurationsdatei *config.ini* wird verwendet, um Ihren Heimatort und das Erscheinungsbild Ihrer Nachbarschaft zu ändern. Standardmäßig ist der Heimatort auf das Berlin Brandenburger Tor eingestellt.

### Standort

Erhalten Sie Ihren Heimatort über [Google Maps](https://www.google.com/maps), klicken Sie auf Ihren gewünschten Standort und überprüfen Sie die URL Ihres Browserfensters:

![google_maps_url](images/google_maps_url.png)

Der Standort ist im Format ```@<latitude>,<longitude>``` codiert. Tragen Sie diese Zahlen in die latitude- und longitude-Felder der config.ini ein.

### Gebietsschema

Wenn Sie möchten, dass die Karten mit einem bestimmten Gebietsschemanamen versehen werden, z. B. Deutsch, legen Sie ```localeLang = de``` und ```localeCountry = DE``` fest oder suchen Sie die richtige Gebietsschemadefinition Ihrer Wahl (siehe [ISO-Gebietsschema-Sprachcodetabelle](https://gist.github.com/eddieoz/63d839c8a20ef508cfa4fa9562632a21)).

## Steuerung

### Tasten

```R```: schaltet die Visualisierung der Regenradarkarte als Overlay um (ein/aus)

```C```: schaltet die Visualisierung der Wolkenkarte als Overlay um (ein/aus)

### Maus

```Mittlere Maustaste``` auf ein beliebiges Flugzeugsymbol im Anwendungsfenster aktiviert das FollowFlight-Fenster für einen bestimmten Flug, um den Flug auf dem Weg zu seinem Ziel zu verfolgen.
