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
from tracking.pubsub_registry import notify_new_tracks


class GsatHandler():
    SENSOR_TYPE = 'gsat'
    SOURCE_TYPE = 'gps-radio'

    gsat_map = {
        'manufacturer_id': lambda o: str(o.get('uniqueid')),
        'location': lambda o: GsatHandler._parse_location(o.get('lat'), o.get('lng')),
        'recorded_at': lambda o: datetime.datetime.fromtimestamp(int(o.get('time')), tz=pytz.UTC),
        'altitude_meters': lambda o: float(o.get('alt')),
        'speed_mps': lambda o: float(o.get('speed')),
        'heading': lambda o: float(o.get('head')),
        'is_emergency': lambda o: True if o.get('isemergency') == '1' else False,
        'events': lambda o: o.get('events').split(',') if len(o.get('events', '')) > 0 else None,
        'sensor_type': lambda o: GsatHandler.SENSOR_TYPE
    }

    @staticmethod
    def _parse_location(lat, lon):
        try:
            return Point(x=float(lon), y=float(lat))
        except:
            return None

    @staticmethod
    def _parse_gsat_request(o):

        r = dict((k, v(o)) for k, v in GsatHandler.gsat_map.items())
        return r

    @staticmethod
    def _default_assigned_range(d1):
        return (d1, d1 + timedelta(days=365 * 5))

    @staticmethod
    def handle_observation(request, provider_key):

        obj = GsatHandler._parse_gsat_request(request.query_params)

        obj['provider_key'] = provider_key

        model_name = '{}:{}'.format(GsatHandler.SENSOR_TYPE, provider_key)
        src, created = Source.objects.ensure_source(GsatHandler.SOURCE_TYPE, obj.get('manufacturer_id'),
                                                    model_name=model_name)
        # If the Source already exists, assume the SubjectSource and Subject already exist.
        if created:
            ss, created = SubjectSource.objects.ensure_subject_source(src,
                                                                      timestamp=obj['recorded_at'],
                                                                      subject_type='person',
                                                                      subject_subtype='ranger',
                                                                      assigned_range=GsatHandler._default_assigned_range(
                                                                          obj['recorded_at'])
                                                                      )

        obj['additional'] = dict((k, obj[k]) for k in obj if k not in ('manufacturer_id', 'location', 'recorded_at',))
        obj['source'] = src.id

        serializer = ObservationSerializer(data=obj)
        if serializer.is_valid():
            serializer.save()

            notify_new_tracks(src.id)

            # GSAT service expects 200 and considers anything else bad.
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
