# Support
Here are the topics and procedures for troubleshooting DAS.

## Tier 1

## Tier 2
### Real-time Feed

#### Troubleshooting
* verify the realtime service is running, by opening a shell on the API server.
```
sudo supervisorctl status
```

## Tier 3
If after review of the logs and or web console we don't have resolution in the Tier 2 and Tier 3 sections we consider it a Tier 3 issue.


## Integrations
The following are the list of devices DAS supports either directly or through the DAS API.

### TRBOnet

* DASRadioAgent
#### Troubleshooting
We are looking for a heartbeat check from the DAS Radio Agent. This is seen as a status check on the DAS API. Look for the user_agent being the das-radio-agent.
```
{"asctime": "2017-09-19 00:01:22,963", "levelname": "INFO", "processName": "MainProcess", "thread": 140472581875456, "na
me": "django.request", "message": "request", "remote_addr": "41.186.69.35, 10.4.1.132", "referer": "", "method": "GET",
"path": "/api/v1.0/status", "content_length": 95, "protocol": "HTTP/1.0", "user_agent": "das-radio-agent/1.0.23.0", "use
r_id": "aaf7bec8-41d0-46ed-b26a-15f506e69d43", "status": 200, "req_time": 0.004650115966796875}
```

Once that is verified, we know the DASRadioAgent is running. Next is to check to see if we have received any radio status updates. Look for POSTS on the DAS API as follows:

```
{"asctime": "2017-09-18 23:54:44,863", "levelname": "INFO", "processName": "MainProcess", "thread": 140472581875456, "name": "django.request", "message": "request", "remote_addr": "41.186.69.35, 10.4.1.132", "referer": "", "method": "POST", "path": "/api/v1.0/sensors/dasradioagent/akagera-trbonet/status", "content_length": 608, "protocol": "HTTP/1.0", "user_agent": "das-radio-agent/1.0.23.0", "user_id": "aaf7bec8-41d0-46ed-b26a-15f506e69d43", "status": 201, "req_time": 0.3037996292114258}
```


### ShadowView
Using a LoRa mesh network, host several different types of low data devices. The first being a tracking device. GPS points are carried to their central hub which in turn sends location updates to DAS through the DAS API.
#### Troubleshooting
Consists of searching the DAS API logs for shadowview. We are looking to see updates from their server.
For example:
````
{"asctime": "2017-09-18 23:58:47,530", "levelname": "INFO", "processName": "MainProcess", "thread": 140472581875456, "name": "django.request", "message": "request", "remote_addr": "41.186.69.35, 10.4.1.132", "referer": "", "method": "POST",
 "path": "/api/v1.0/sensors/generic/shadowview/status", "content_length": 22923, "protocol": "HTTP/1.0", "user_agent": "
Java/1.8.0_131", "user_id": "853d4c80-7ce9-4ee4-8ba6-64c65ce4b616", "status": 201, "req_time": 0.4786038398742676}
````

### AWT
[Africa Wildlife Tracking](http://www.awt.co.za/)
There are several companies AWT works with to download collar tracking data. See Skygistics and AWE below for specifics.

Sophie Haupt is our point of contact at AWT.
 
### Savannah Tracking
[Savannah Tracking](http://www.savannahtracking.com/)


### SirTrack

### TAACP

### Spider Tracks
[Spider Tracks](http://www.spidertracks.com/)

### Garmin inReach
[Garmin inReach](https://explore.garmin.com/en-US/inreach/) Previously owned by Delorme, the inReach is a satellite based tracking devices with SMS text messaging.
A device under an enterprise subscription plan allows DAS to communicate with the inReach API to access the devices location.

### Skygistics (AWT)
Skygistics is the satellite downlink and API provider for this AWT collar.

### AWE (AWT)
[AWE](http://www.awetelemetry.com/) is the satellite downlink and API provider for this AWT collar.

### Vectronics
[Vectronics](http://www.vectronic-aerospace.com/wildlife-monitoring/vectronic-wildlife/) satellite collar tracking company. A windows based application downloads the track data into a PostgreSQL database. DAS directly accesses the vectronics db to move track data into DAS.

To support DAS, we run the GPS Plus X collar manager software on a windows platform hosted by the same cloud provider as DAS itself. We configure the GPS Plus machine to communicate with the same PostgreSQL database server as DAS to reduce cost. As long as DAS can reach the GPS Plus PostgreSQL db, then DAS can download track data.


#### Troubleshooting
Ensure the GPS Plus X collar manager software is running and able to download from Vectronics.


### GSAT
[GSAT](http://www.gsat.us/)

This is a white labeled satellite radio with Location tracking. Also known as Nano radios.
A callback from their web service communicates with our API to send location updates. 

#### Troubleshooting
Review the DAS API logs for signs that GSAT has POSTed updates on the DAS API:

```

```