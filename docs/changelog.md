# Releases


## Release 1.25.5 2017-12-11

This deployment will consist of these recent features and fixes:
* Jump to Location of an Incident
  * From the feed, you can now jump to the location of an incident.  If the Incident contains multiple reports, the map will zoom to display all reports.
* New Incident Icons Displaying First Report
  * An incident icon will now embed the icon of the first report to make the content of the incident more clear
* Improved Image Viewer in App
  * A new image viewer in included to view the image within the DAS app
* Additional Zoom Level on Map
  * When viewing Satellite maps, there is one additional level of zoom 
* Edit Notes
  * Notes in Reports and Incidents can now be edited
* Sort Reports in an Incident by Creation Date
  * Reports included in an incident are now clearly sorted by the date they were created
* Location Entry Help Text
  * Helper text is available when locations are manually entered on a report.  
* Panthera Camera Trap Support
  * Panthera Cameras can now interface to DAS creating reports with included images
* Fix for Queues backing up causing delayed subject position updates
  * Eliminates the situation where subject position updates are blocked
* Fix for Database Connections causing inability to log into DAS
  * Eliminates the situation where users can’t log in due to a “undefined” error message
* hotfix for track data error in STE App.



## Release 1.18
### Overview
Support SMS output for alerts. Simplify template used to render SMS txt.
Fix bug in vectronics collar data import ensuring the source record. Prevented new data from being added to db.
Fix bug in web editing an existing report that contained a number field in the data model. A null value in the number field was not handled, causing the report to not be displayed. Resolved reports displayed correctly.
Fix bug showing fields that changed in an alert email so that a consolidate alert email correctly shows all fields that changed over multiple edits. Today only the last change is annotated in an alert email.




## Release 1.17

### Overview
Fix bug when creating a new Report, the previous data model schema was used.


## Release 1.16

### Overview

Filter reports displayed in the Reports feed, so that reports contained in an incident are not displayed.
Consolidate alert emails so that consecutive changes to a Report in a short amount of time do not generate multiple email updates.
Choice tables for Liwonde (a few spoor related tables orphaned on an old branch)
Fix bug that was escaping "&" signs in report titles. We clean any text typed in by a user looking for HTML based attacks.
Fix bug preventing a report appearing in an alert email when an incident only had one report. 

### DAS Web Change Log ###
__1\.16\.1\.rc\.3__

<li> <a href=http://github.com/padas/das-web/commit/d922343ea445da4d718b71a148bb3b556dfbae0a>view commit &bull;</a> new parameter for the new events feed to exclude reports that are contained in collections.</li> 
<li> <a href=http://github.com/padas/das-web/commit/988dd9cd5c5b9b130f05db39ead219b2c6d019e4>view commit &bull;</a> creating a new collection with an existing report should inherit priority (#115)</li> 
<li> <a href=http://github.com/padas/das-web/commit/80afe774435d77b0db8aaaeb0efb3a458afc826d>view commit &bull;</a> Feature/incident feed bugs1 (#116)</li> 
<li> <a href=http://github.com/padas/das-web/commit/6d21ba7a7ddc6063885decbc593afb249be3417d>view commit &bull;</a> exclude contained reports in Resolved and All feeds</li> 
<li> <a href=http://github.com/padas/das-web/commit/c527aac9d965a3844f703a422cf308edfa041853>view commit &bull;</a> filter contained events in the 'all' feed.</li> 


### DAS Server Change Log ###
__1\.16\.1\.rc\.14__
<li> <a href=http://github.com/padas/das/commit/185156894fdd1c4eba4703e9dc1d8c0c01b2b95c>view commit &bull;</a> Update __init__.py</li> 
<li> <a href=http://github.com/padas/das/commit/33e509bb8b9875c94741457c51411d27a2fb4449>view commit &bull;</a> Move version to 1.16 on develop</li> 
<li> <a href=http://github.com/padas/das/commit/543366a028bba2dfbfe0f174201cc4856bb569b0>view commit &bull;</a> Add plugin model for SirTrack integration</li> 
<li> <a href=http://github.com/padas/das/commit/4fce65cca8efb63da207d659a3b7e6698fa54430>view commit &bull;</a> Process SirTrack CSV as stream, with long read timeouts.</li> 
<li> <a href=http://github.com/padas/das/commit/bcc932e176ba71388e46e5271831622e9f470081>view commit &bull;</a> Bump commit she for fastkml.</li> 
<li> <a href=http://github.com/padas/das/commit/6a26888e8fc26d360dee10dad3652feff01953b5>view commit &bull;</a> Add sirtrack unit tests.</li> 
<li> <a href=http://github.com/padas/das/commit/34f9c2a34e43bef40e0c174d6fe5e5213c761798>view commit &bull;</a> Purge events command.</li> 
<li> <a href=http://github.com/padas/das/commit/f3ee61e7aa764e08d4b52908d849b8a43e38e647>view commit &bull;</a> Clean up logging in exception handlers.</li> 
<li> <a href=http://github.com/padas/das/commit/570bbfbeae6d8fb148c43aae0c73b2f6eefe2b63>view commit &bull;</a> Updates to alerts specified in DAS 1795</li> 
<li> <a href=http://github.com/padas/das/commit/fe2cecfe313b63997ee2fc8f9dd0e01150273c84>view commit &bull;</a> updated docker config for alerts</li> 
<li> <a href=http://github.com/padas/das/commit/efb2dd2c2fb7e780cca09b8455f38757723a80cb>view commit &bull;</a> event api qparam to exclude contained items.</li> 
<li> <a href=http://github.com/padas/das/commit/e9418bc4145f1fd600e6fea1d9f595dfe1eb4c94>view commit &bull;</a> rename events qparam to exclude_contained</li> 
<li> <a href=http://github.com/padas/das/commit/e4634e73b8fc3b53c2375267386aa0de9bff7280>view commit &bull;</a> Update email config for docker containers running on gcp</li> 
<li> <a href=http://github.com/padas/das/commit/42d675e30fd74f5f2941030d0b650e3a0ba96dd7>view commit &bull;</a> clean up settings a little</li> 
<li> <a href=http://github.com/padas/das/commit/33b0a1c672af29c217fa7fd17a152d72fc96f654>view commit &bull;</a> Revert "Update email config for docker containers running on gcp"</li> 
<li> <a href=http://github.com/padas/das/commit/a1f92a3c75082debf76b233c62b625b76f89d63b>view commit &bull;</a> updates to pipeline info for automation. MK</li> 
<li> <a href=http://github.com/padas/das/commit/3fbfa5398d0fc5218e3a2d9b76ed29974d9e53c8>view commit &bull;</a> Changes to pipeline for env dirs and relative path fixes. MK SH CJ</li> 
<li> <a href=http://github.com/padas/das/commit/3f7b355ea1bf1e0e401463d1e257b56b71ef2df3>view commit &bull;</a> Making tag as latest a variable for the multi pipeline world. MK CLJ SH</li> 
<li> <a href=http://github.com/padas/das/commit/b71efcddf97cc208c22fdb71fb607486d7e2813c>view commit &bull;</a> release candidate version</li> 
<li> <a href=http://github.com/padas/das/commit/3456d8bce2dd0e5c441e907d62b9b4b43c0a1369>view commit &bull;</a> Fix bug that prevented child event details from being included in parent email alert</li> 
<li> <a href=http://github.com/padas/das/commit/7793c82a1bc34c742a7a82e746fdb3aef7309593>view commit &bull;</a> Skip alerts for events with parent, we'll update for the parent anyway</li> 
<li> <a href=http://github.com/padas/das/commit/23dd4c408eda30ad6cc4cd43cbc97f9559a8a80c>view commit &bull;</a> missing dog team and boat in release.</li> 
<li> <a href=http://github.com/padas/das/commit/8342d2a7cc5f7fbc79315c29c8916af2c22ec71c>view commit &bull;</a> missing dog team and boat in release, migration for those new choices</li> 
<li> <a href=http://github.com/padas/das/commit/a75d03d2c0249d91d1afb2112799138e33bc5f39>view commit &bull;</a> added camera trap and radio report icons</li> 
<li> <a href=http://github.com/padas/das/commit/ff353d6fb743faddb71676b07df447353e18ed09>view commit &bull;</a> consolidate alerts by waiting a few seconds for additional changes before sending an alert</li> 
<li> <a href=http://github.com/padas/das/commit/23d2e4d2d5acfde4eb4ec6aa42e18736649226c5>view commit &bull;</a> Fix reference to alert utils</li> 
<li> <a href=http://github.com/padas/das/commit/08434de015ae255ca3a54dd40fd123d7124cd0df>view commit &bull;</a> Fix merge conflict related to how call to email is made</li> 
<li> <a href=http://github.com/padas/das/commit/dcee531f5e1bddf8495de2c897f9d628dc15ab0d>view commit &bull;</a> CR updates for alert consolidation</li> 
<li> <a href=http://github.com/padas/das/commit/df175cbb43190d31c7df3c95aff84959fc4c8028>view commit &bull;</a> Fix bug when queueing a celery task using delay</li> 
<li> <a href=http://github.com/padas/das/commit/77808b548b669ac8500a1cc7322a1053b2c3c24d>view commit &bull;</a> Fix bug that prevented child emails from showing up in alert emails if there was only one single child</li> 



## Release 1.15

### Overview

This release incorporates redesigned UI in support of Input Report collections and streamlined data entry\.

### DAS Web Change Log ####

__1\.15\.1 Final__

__1\.15\.1\.rc\.48__

at some point created\_at was changed to time\. update created\_at

__1\.15\.1\.rc\.47__

show/hide event names was not being honored when:

+ starting up,

+ map panned/zoomed (leaflet\-cached markers)

+ events loaded on map moves/zooms

+ reports group toggled on/off

+ report types toggled on\-off\.
 note: still doesn't work when clusters expanded, and more testing required

__1\.15\.1\.rc\.46__

fixes Add Marker and Ruler map tools bugs on touchscreen (ALL grumeti screens):

+ cancel/esc no longer turns features off and leaves them off\.

+ If you start with features off, adding a marker no longer turns features on and leaves them on\.

+ If you start with features off, using the ruler no longer leaves features on and leaves them on\.

__1\.15\.1\.rc\.45__

NEW ICONS
const kDasEvent\_burn\_rep = 'burn\_rep'; // 1\.15 grumeti
const kDasEvent\_plant\_control\_rep = 'plant\_control\_rep'; // 1\.15 grumeti
const kDasEvent\_scholarship = 'scholarship'; // 1\.15 grumeti
const kDasEvent\_HWC\_follow\_up = 'HWC\_follow\_up'; // 1\.15 grumeti, dup of kDasEvent\_hwc\_rep
const kDasEvent\_tse\_tse\_status = 'tse\_tse\_status'; // 1\.15 grumeti
const kDasEvent\_migration\_rep = 'migration\_rep'; // 1\.15 grumeti
const kDasEvent\_rhino\_boma\_rep = 'rhino\_boma\_rep'; // 1\.15 grumeti
const kDasEvent\_hwc\_alert\_rep = 'hwc\_alert\_rep'; // 1\.15 grumeti new, see kDasEvent\_HWC\_follow\_up & kDasEvent\_hwc\_rep\. TODO\_RECONCILE\_WITH\_AP

REPORT PRIORITY CHANGES (GRUMETI ONLY)
wildlife mort green (was yellow)\. TODO\_RECONCILE\_WITH\_AP
hwc follow up grey (CURRENTLY RED)
hwc alert (?)
alien plant infestation yellow (was green)
arrest is grey (was green)
salta red (was yellow)
mist red (was grey) (all 3 moved\. lewa doesn't use)
spoor report amber (was grey)

__1\.15\.1\.rc\.44__

+ update sit\_rep to radio\_rep

### DAS Server Change Log ####

__1\.15\.2 Final__
Hotfix to show the correct version number 1.15.2

__1\.15\.1 Final__

__1\.15\.1\.rc\.67__

+  add giraffe icon

__1\.15\.1\.rc\.67__

+ Updates to daily report and templates, to reflect changes in Lewa data

__1\.15\.1\.rc\.65__

+  fix logging exceptions in rt\_api server\. The log format was incorrect forcing multiple errors in the logs

+ adding migration, scholarship, plant\_control, burn and updated rhino\_boma event type icons

__1\.15\.1\.rc\.63__

