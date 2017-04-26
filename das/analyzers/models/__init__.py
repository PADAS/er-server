import uuid

from django.contrib.gis.db import models
from django.utils.translation import ugettext_lazy as _

from analyzers.models.annotation import ObservationAnnotator
from analyzers.models.immobility import ImmobilityAnalyzer
from analyzers.models.analyzer import SubjectAnalyzerResult
from core.models import TimestampedModel

all_analyzers = (
    ImmobilityAnalyzer,
)



