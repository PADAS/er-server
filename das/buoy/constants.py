# Constants for buoy gearset and device management

# New Data Model Subject Subtype for buoy gearsets
BUOY_GEAR_SUBJECT_SUBTYPE = "ropeless_buoy_gearset"
# Old Data Model Subject Subtype for buoy devices
BUOY_DEVICE_SUBJECT_SUBTYPE = "ropeless_buoy_device"

SOURCE_TYPE = "ropeless_buoy"

# Event types for trap deployment tracking
TRAP_DEPLOYED = "trap_deployed"
TRAP_RETRIEVED = "trap_retrieved"

DISPLAY_ID_KEY = "display_id"
DEVICES_KEY = "devices"
ID_KEY = "id"
STATUS_KEY = "status"
SUBJECT_KEY = "subject"

# Gear types for buoy devices
GEAR_TYPE_TRAWL = "trawl"
GEAR_TYPE_SINGLE = "single"
GEAR_TYPE_SURFACE = "surface"

# Device deployment statuses
DEVICE_STATUS_DEPLOYED = "deployed"
DEVICE_STATUS_HAULED = "hauled"
DEVICE_STATUS_LOST = "lost"

# Release types for buoy devices
RELEASE_TYPE_TIMED = "timed"
RELEASE_TYPE_GALVANIC = "galvanic"
RELEASE_TYPE_ACOUSTIC = "acoustic"

# Positioning types for buoy devices
POSITIONING_TYPE_GPS = "gps"
POSITIONING_TYPE_ACOUSTIC = "acoustic"


# Choices
DEPLOYMENT_TYPE_CHOICES = [
    (GEAR_TYPE_TRAWL, GEAR_TYPE_TRAWL),
    (GEAR_TYPE_SINGLE, GEAR_TYPE_SINGLE),
    (GEAR_TYPE_SURFACE, GEAR_TYPE_SURFACE),
]

DEVICE_DEPLOYMENT_STATUS_CHOICES = [
    (DEVICE_STATUS_DEPLOYED, DEVICE_STATUS_DEPLOYED),
    (DEVICE_STATUS_HAULED, DEVICE_STATUS_HAULED),
    (DEVICE_STATUS_LOST, DEVICE_STATUS_LOST),
]

RELEASE_TYPE_CHOICES = [
    (RELEASE_TYPE_TIMED, RELEASE_TYPE_TIMED),
    (RELEASE_TYPE_ACOUSTIC, RELEASE_TYPE_ACOUSTIC),
    (RELEASE_TYPE_GALVANIC, RELEASE_TYPE_GALVANIC),
]

POSITIONING_TYPE_CHOICES = [
    (POSITIONING_TYPE_GPS, POSITIONING_TYPE_GPS),
    (POSITIONING_TYPE_ACOUSTIC, POSITIONING_TYPE_ACOUSTIC),
]
