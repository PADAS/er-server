## Releases


### Release 1\.15

#### Overview

This release incorporates redesigned UI in support of Input Report collections and streamlined data entry\.

#### DAS Web Change Log ####

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

#### DAS Server Change Log ####

__1\.15\.1\.rc\.67__

+  add giraffe icon

__1\.15\.1\.rc\.67__

+ Updates to daily report and templates, to reflect changes in Lewa data

__1\.15\.1\.rc\.65__

+  fix logging exceptions in rt\_api server\. The log format was incorrect forcing multiple errors in the logs

+ adding migration, scholarship, plant\_control, burn and updated rhino\_boma event type icons

__1\.15\.1\.rc\.63__

##### Builds #####

das server: [http://tools\.pamdas\.org:8080/view/Production/job/das\-server\-build\-release1\.15\.1/](http://tools\.pamdas\.org:8080/view/Production/job/das\-server\-build\-release1\.15\.1/)

das web: [http://tools\.pamdas\.org:8080/view/Production/job/das\-web\-build\-release1\.15\.1/](http://tools\.pamdas\.org:8080/view/Production/job/das\-web\-build\-release1\.15\.1/)
