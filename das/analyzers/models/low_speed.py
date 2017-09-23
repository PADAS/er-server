from django.contrib.gis.db import models
from analyzers.models.base import SubjectAnalyzerConfig

class LowSpeedAnalyzerConfig(SubjectAnalyzerConfig):

    low_threshold_percentile = models.FloatField(null=False, default=0.01)

    # the default value to use when there is no speed_profile available
    # should set this to the global median low speed value for the corresponding percentile
    default_value = models.FloatField(null=False, default=0.05)  # 0.05 Km/Hr
