import datetime
from datetime import timedelta

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
import pytz
from django.contrib.gis.geos import Point

from observations.models import Source, SubjectSource, Subject, Source
from observations.serializers import ObservationSerializer

def _default_assigned_range(d1):
    return (d1, d1 + timedelta(days=365))

def _parse_location(lat, lon):
    try:
        return Point(x=float(lon), y=float(lat))
    except:
        return None

gsat_map = {
    'manufacturer_id': lambda o: str(o.get('uniqueid')),
    'location': lambda o: _parse_location(o.get('lat'), o.get('lng')),
    'recorded_at': lambda o: datetime.datetime.fromtimestamp(int(o.get('time')), tz=pytz.UTC),
    'altitude_meters': lambda o: float(o.get('alt')),
    'speed_mps': lambda o: float(o.get('speed')),
    'heading': lambda o: float(o.get('head')),
    'is_emergency': lambda o: True if o.get('isemergency') == '1' else False,
    'events': lambda o: o.get('events').split(',') if len(o.get('events', '')) > 0 else None
}

def _parse_gsat_request(o, m):
    r = dict((k, v(o)) for k, v in m.items())
    return r

@api_view(['GET', 'POST'])
@permission_classes((AllowAny,))
def observation_list(request, sensor_type=None, provider_key=None):
    """
    For a manufacturer_id:
        list some observations, or create a new observation.
    """

    if request.method == 'GET':

        qp = request.query_params

        obj = _parse_gsat_request(qp, gsat_map)

        source_type = 'gps-radio'

        src, created = Source.objects.ensure_source(source_type, obj.get('manufacturer_id'))

        if created:
            ss, created = SubjectSource.objects.ensure_subject_source(src,
                                                             timestamp=obj['recorded_at'],
                                                             subject_type='person',
                                                             subject_subtype='ranger',
                                                             assigned_range=_default_assigned_range(obj['recorded_at'])
                                                             )

        obj['additional'] = dict((k, obj[k]) for k in obj if k not in ('manufacturer_id', 'location', 'recorded_at',))
        obj['source'] = src.id
        serializer = ObservationSerializer(data=obj)
        if serializer.is_valid():
            serializer.save()

            # GSAT service expects 200 and considers anything else bad.
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


