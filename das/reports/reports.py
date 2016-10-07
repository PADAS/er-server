from datetime import datetime, timedelta
import pytz
import json
from django.db.models import *
from activity.models import Event
from choices.models import Conservancy

def get_events(start, end):
    events = Event.objects.filter(event_time__range=[start,end]).prefetch_related('event_type', 'reported_by')
    return events

def get_conservancies():
    return Conservancy.objects.all().values()



