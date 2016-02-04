from .models.geofence import GeofenceAnalyzer
from .models.immobility import ImmobilityAnalyzer
from .models.speed import SpeedAnalyzer
from .models.proximity import ProximityAnalyzer

all_analyzers = (
    GeofenceAnalyzer(),
    ImmobilityAnalyzer(),
    SpeedAnalyzer(),
    ProximityAnalyzer()
)
