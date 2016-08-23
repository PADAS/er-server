import datetime
from datetime import timedelta
import logging
import pytz
from dateutil.parser import parse as parse_date

from rest_framework import status
from rest_framework.response import Response
from django.contrib.gis.geos import Point

from observations.models import Source, SubjectSource, Subject, Source, Observation
from observations.serializers import ObservationSerializer
from tracking.pubsub_registry import notify_new_tracks


class DasRadioAgentHandler():
    SENSOR_TYPE = 'dasradioagent'
    SOURCE_TYPE = 'gps-radio'
    DEFAULT_SUBJECT_TYPE = 'person'
    DEFAULT_SUBJECT_SUBTYPE = 'ranger'

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

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
        return dt

    @staticmethod
    def _default_assigned_range(d1):
        rng = (d1, d1 + timedelta(days=365 * 5))
        return list(rng)

    def handle_observation(self, request, provider_key):

        obj = request.data

        location = None
        try:
            location = obj.get('location')
            lat = location.get('lat', None)
            lon = location.get('lon', None)

            location = Point(x=float(lon), y=float(lat))
        except:
            location = None

        model_name = '{}:{}'.format(self.SENSOR_TYPE, provider_key)
        manufacturer_id = obj.get('manufacturer_id')
        src, created = Source.objects.ensure_source(self.SOURCE_TYPE, manufacturer_id=manufacturer_id,
                                                    model_name=model_name)

        recorded_at = self.__str2date(obj['recorded_at'])

        # Short-circuit if we already have this observation.
        if Observation.objects.filter(source=src, recorded_at=recorded_at).exists():
            return Response({}, status=status.HTTP_201_CREATED)

        # If the Source already exists, assume the SubjectSource and Subject already exist.
        if created:

            ss, created = SubjectSource.objects.ensure_subject_source(src,
                                                                      timestamp=recorded_at,
                                                                      subject_type=self.DEFAULT_SUBJECT_TYPE,
                                                                      subject_subtype=self.DEFAULT_SUBJECT_SUBTYPE,
                                                                      assigned_range=self._default_assigned_range(
                                                                          recorded_at),
                                                                      subject_name=obj.get('subject_name', manufacturer_id)
                                                                      )

        observation = {
            'location': location,
            'recorded_at': recorded_at,
            'source': src.id,
            'additional': obj['additional'],
        }

        # Anything else that was included in the posted object should move into additional.
        observation['additional'].update(dict((k, obj[k]) for k in obj if k not in observation.keys()))

        serializer = ObservationSerializer(data=observation)
        if serializer.is_valid():
            serializer.save()
            notify_new_tracks(src.id)
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
        'recorded_at': lambda o: GsatHandler._parse_gsat_timestamp(o),
        'altitude_meters': lambda o: float(o.get('alt', 0)),
        'speed_mps': lambda o: float(o.get('speed', 0)),
        'heading': lambda o: float(o.get('head', 0)),
        'is_alarm': lambda o: True if o.get('emer') == '1' else False,
        'events': lambda o: o.get('events').split(',') if len(o.get('events', '')) > 0 else None,
        'sensor_type': lambda o: GsatHandler.SENSOR_TYPE
    }

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def _parse_location(lat, lon):
        try:
            return Point(x=float(lon), y=float(lat))
        except:
            raise

    @staticmethod
    def _parse_gsat_request(o):

        r = dict((k, v(o)) for k, v in GsatHandler.gsat_map.items())
        return r

    @staticmethod
    def _parse_gsat_timestamp(obj):
        try:
            return datetime.datetime.fromtimestamp(int(obj.get('time')), tz=pytz.UTC)
        except:
            return datetime.datetime.now(tz=pytz.UTC)


    @staticmethod
    def _default_assigned_range(d1):
        return (d1, d1 + timedelta(days=365 * 5))

    REQUIRED_PARAMS = ('uniqueid', 'lat', 'lng', 'time',)
    OPTIONAL_PARAMS = ('alt', 'head', 'speed', 'emer',)

    @staticmethod
    def _validate_template_request(qp):
        template = {
            'uniqueid': '{uniqueid}',
            'lat': '{lat}',
            'lng': '{lng}',
            'time': '{time}',
            'alt': '{altitude}',
            'head': '{heading}',
            'speed': '{speed}',
            'emer': '{isemergency}'
        }

        if all (qp[k] == template[k] for k in qp if k in template) \
            and all(_ in qp for _ in GsatHandler.REQUIRED_PARAMS):
            return True

    def handle_observation(self, request, provider_key):

        self.logger.info('Gsat request: {}'.format(request.query_params))

        try:
            obj = GsatHandler._parse_gsat_request(request.query_params)
        # except ValueError as ve:
        except Exception as e:
            if self._validate_template_request(request.query_params):
                return Response({'data': 'That looks like a valid template request'})
            else:
                return Response({'data': 'Check query parameters and try again.'}, status=status.HTTP_400_BAD_REQUEST)

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
