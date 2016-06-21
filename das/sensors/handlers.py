import datetime
from datetime import timedelta
import pytz
from dateutil.parser import parse as parse_date

from rest_framework import status
from rest_framework.response import Response
from django.contrib.gis.geos import Point

from observations.models import Source, SubjectSource, Subject, Source
from observations.serializers import ObservationSerializer
from tracking.pubsub_registry import notify_new_tracks


class DasRadioAgentHandler():
    SENSOR_TYPE = 'dasradioagent'
    SOURCE_TYPE = 'gps-radio'
    DEFAULT_SUBJECT_TYPE = 'person'
    DEFAULT_SUBJECT_SUBTYPE = 'ranger'

    def _parse_location(self, o):
        try:
            loc = o.get('location')
            return Point(x=float(loc.get('longitude')), y=float(loc.get('latitude')))
        except:
            return None

    @staticmethod
    def __str2date(d, default_tzinfo=pytz.UTC):
        '''Parse a date and if it's naive, replace tzinfo with default_tzinfo.'''
        dt = parse_date(d)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=default_tzinfo)

    def handle_observation(self, request, provider_key):

        try:
            location = request.data.get('location')
            lat = location.get('lat', None)
            lon = location.get('lon', None)

            location = Point(x=float(lon), y=float(lat))
        except:
            location = None

        manufacturer_id = request.data.get('manufacturer_id', None)
        source_type = request.data.get('source_type', None)

        if not manufacturer_id or not source_type:
            return Response(data="Missing parameters. Please provide both 'manufacturer_id' and 'source_type'.",
                            status=status.HTTP_400_BAD_REQUEST)

        recorded_at = request.data.get('recorded_at')
        recorded_at = self.__str2date(recorded_at)
        src = Source.objects.ensure_source(source_type, manufacturer_id)
        ss = SubjectSource.objects.ensure_subject_source(src, timestamp=recorded_at,
                                                         subject_name=request.get('subject_name'))

        additional = request.data.get('additional', {})
        additional.update(dict(k,v)
                          for k, v in request.data.items() if k not in ('location', 'recorded_at', 'additional'))

        observation_data = {
            'location': location,
            'recorded_at': recorded_at,
            'source': src.id,
            'additional': request.data.get('additional', {}),
        }


        serializer = ObservationSerializer(data=observation_data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GsatHandler():
    SENSOR_TYPE = 'gsat'
    SOURCE_TYPE = 'gps-radio'
    DEFAULT_SUBJECT_TYPE = 'person'
    DEFAULT_SUBJECT_SUBTYPE = 'ranger'

    gsat_map = {
        'manufacturer_id': lambda o: str(o.get('uniqueid')),
        'location': lambda o: GsatHandler._parse_location(o.get('lat'), o.get('lng')),
        'recorded_at': lambda o: datetime.datetime.fromtimestamp(int(o.get('time')), tz=pytz.UTC),
        'altitude_meters': lambda o: float(o.get('alt')),
        'speed_mps': lambda o: float(o.get('speed')),
        'heading': lambda o: float(o.get('head')),
        'is_alarm': lambda o: True if o.get('isemergency') == '1' else False,
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

    def handle_observation(self, request, provider_key):

        obj = GsatHandler._parse_gsat_request(request.query_params)

        obj['provider_key'] = provider_key

        model_name = '{}:{}'.format(GsatHandler.SENSOR_TYPE, provider_key)
        src, created = Source.objects.ensure_source(self.SOURCE_TYPE, obj.get('manufacturer_id'),
                                                    model_name=model_name)
        # If the Source already exists, assume the SubjectSource and Subject already exist.
        if created:
            ss, created = SubjectSource.objects.ensure_subject_source(src,
                                                                      timestamp=obj['recorded_at'],
                                                                      subject_type=self.DEFAULT_SUBJECT_TYPE,
                                                                      subject_subtype=self.DEFAULT_SUBJECT_SUBTYPE,
                                                                      assigned_range=self._default_assigned_range(
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
