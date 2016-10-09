from datetime import datetime, timedelta
import pytz
import json
from django.db.models import *
from activity.models import Event
from choices.models import Conservancy
from observations.models import Subject
def get_events(start, end):
    events = Event.objects.filter(event_time__range=[start,end]).prefetch_related('event_type', 'reported_by')
    return events

def get_conservancies():
    return Conservancy.objects.all().values()

def get_rhino_sightings(start, end):
    events = Event.objects.filter(event_type__value__in=('black_rhino_sighting', 'white_rhino_sighting'), event_time__range=[start,end])
    return events

def get_rhinos():
    rhinos = Subject.objects.filter(subject_type=Subject.TYPE_WILDLIFE, subject_subtype=Subject.SUBTYPE_RHINO)
    return rhinos