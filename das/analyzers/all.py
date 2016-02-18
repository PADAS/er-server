from .models.containment import ContainmentAnalyzer
from .models.geofence import GeofenceAnalyzer
from .models.immobility import ImmobilityAnalyzer
from .models.proximity import ProximityAnalyzer
from .models.speed import SpeedAnalyzer

all_analyzers = (
    ContainmentAnalyzer,
    GeofenceAnalyzer,
    ImmobilityAnalyzer,
    SpeedAnalyzer,
    ProximityAnalyzer
)
