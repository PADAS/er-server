Collars and Sensors integrated with ER
==================================================================

## Radios

### MOTOTRBO Radios via TRBOnet (software interface to MOTOTRBO radios)
[TRBOnet](https://trbonet.com/)

### Garmin inReach
[Garmin inReach](https://explore.garmin.com/en-US/inreach/) Previously owned by Delorme, the inReach is a satellite based tracking devices with SMS text messaging.
A device under an enterprise subscription plan allows ER to communicate with the inReach API to access the devices location.

### GSAT
[GSAT](http://www.gsat.us/)

This is a white labeled satellite radio with Location tracking. Also known as Nano radios.
A callback from their web service communicates with our API to send location updates. 

## Vehicle Tracking

### Smart Parks
Using a LoRa network, [Smart Parks](https://www.theinternetoflife.com/) has pioneered several different types of low data devices. The first being a tracking device. GPS points are carried to their central hub which in turn sends location updates to ER through the ER API.
The first tracking devices were used on vehicles, secondly they have designed one to be implanted in a Rhino horn.

### Spider Tracks
[Spider Tracks](http://www.spidertracks.com/)
Aircraft tracking system. 

## Tracking Collars

### AWT
[Africa Wildlife Tracking](http://www.awt.co.za/)
There are several companies AWT works with to download collar tracking data. See Skygistics and AWE below for specifics.

Sophie Haupt is our point of contact at AWT.

### Skygistics (AWT)
Skygistics is the satellite downlink and API provider for this AWT collar.

### AWE (AWT)
[AWE](http://www.awetelemetry.com/) is the satellite downlink and API provider for this AWT collar.


### Savannah Tracking
[Savannah Tracking](http://www.savannahtracking.com/)


### SirTrack
Animal tracking colar manufacturer we support.
[SirTrack](http://www.sirtrack.co.nz/index.php/terrestrialmain/gps/collar)

### TAACP
Somewhat experimental system using RFID dots and RFID sensors in the field to track animal movements. Primarily for Rhino tracking.

[CWS-I](http://cws-i.com/)

TAACP posts observation updates to the ER API.


### Vectronics
[Vectronics](http://www.vectronic-aerospace.com/wildlife-monitoring/vectronic-wildlife/) satellite collar tracking company. A windows based application downloads the track data into a PostgreSQL database. ER directly accesses the vectronics db to move track data into ER.

To support ER, we run the GPS Plus X collar manager software on a windows platform hosted by the same cloud provider as ER itself. We configure the GPS Plus machine to communicate with the same PostgreSQL database server as ER to reduce cost. As long as ER can reach the GPS Plus PostgreSQL db, then ER can download track data.

## Camera Traps

### Panthera Camera Trap
Panthera produces a custom camera trap that works in daylight and nighttime conditions.
Pictures are sent back to their server over a GSM network. Their server than posts the picture to the ER API and appears in ER as a new Camera Trap Report.

### TrailGuard Camera Trap
TrailGuard by Resolve is custom camera trap vendor. Simialar to Panthera, images captured are posted to the ER API and appear in ER as a new Camera Trap Report.

[Wildland Security](http://wildlandsecurity.org/)
[TrailGuard](https://www.leonardodicaprio.org/resolve-trailguard-ground-sensors-for-advanced-conservation-monitoring/)
[Resolve](http://www.resolv.org/site-BiodiversityWildlifeSolutions/)