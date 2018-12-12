import datetime
import logging
import pytz
from dateutil.parser import parse as parse_date

from rest_framework import status
from rest_framework.response import Response

from rest_framework import serializers

from observations.models import SubjectSource, Source, Observation
from observations.serializers import ObservationSerializer
from observations import servicesutils
from observations.models import update_subject_status_from_post
from tracking.pubsub_registry import notify_new_tracks
from sensors.vehicle_tracker import SkylineObservations, SkylineAdapter,\
    FollowltObservation, TractAdapter, TractVehicleData

logger = logging.getLogger(__name__)


class SensorPostParameters(serializers.Serializer):
    location = serializers.DictField()
    recorded_at = serializers.DateTimeField()
    manufacturer_id = serializers.CharField()

    subject_name = serializers.CharField(default=None)
    subject_type = serializers.CharField(default=None)  # Legacy key
    subject_subtype = serializers.CharField(default=None)
    model_name = serializers.CharField(default=None)
    source_type = serializers.CharField(default=None)
    additional = serializers.DictField(default={})


class GenericSensorHandler():

    DEFAULT_SOURCE_TYPE = 'gps-radio'
    DEFAULT_SUBJECT_SUBTYPE = 'ranger'

    @classmethod
    def post(cls, request, sensor_type, provider_key):

        params = SensorPostParameters(data=request.data)
        if not params.is_valid():
            return Response(data=params.errors, status=status.HTTP_400_BAD_REQUEST)

        params = params.validated_data
        manufacturer_id = params['manufacturer_id']
        location = None
        try:
            location = params['location']
            lat = location.get('lat', None)
            lon = location.get('lon', None)

            # location = Point(x=float(lon), y=float(lat))
            location = {'latitude': float(lat), 'longitude': float(lon)}
        except:
            location = None

        subject_subtype = params.get(
            'subject_subtype', cls.DEFAULT_SUBJECT_SUBTYPE)

        source_type = params.get('source_type', provider_key)
        model_name = params.get('model_name', None) or '{}:{}'.format(
            sensor_type, provider_key)

        subject_name = params.get('subject_name') or manufacturer_id

        src = Source.objects.ensure_source(source_type,
                                           provider=provider_key,
                                           manufacturer_id=manufacturer_id,
                                           model_name=model_name,
                                           subject={
                                               'subject_subtype_id': subject_subtype,
                                               'name': subject_name
                                           }
                                           )

        recorded_at = params.get('recorded_at')
        additional = params.get('additional', {})

        # Short-circuit if we already have this observation.
        if Observation.objects.filter(source=src, recorded_at=recorded_at).exists():
            logger.info("Processed duplicate observation %s",
                        subject_subtype, extra={'obs.dup': provider_key})
            return Response({}, status=status.HTTP_201_CREATED)

        observation = {
            'location': location,
            'recorded_at': recorded_at,
            'source': str(src.id),
            'additional': additional,
        }

        serializer = ObservationSerializer(data=observation)
        if serializer.is_valid():
            serializer.save()
            logger.info("Added new observation %s", observation,
                        extra={'obs.new': provider_key})
            notify_new_tracks(src.id)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FollowltTrackerHandler:

    SENSOR_TYPE = 'animal-collar-push'

    @staticmethod
    def convert_to_das_format(data):
        location = {'latitude': data.get('lat'), 'longitude': data.get('lng')}
        try:
            recorded_at = parse_date(data.get('date'))
        except Exception as e:
            logger.error(e)
            raise e
        additional = dict()
        for key in data.keys():
            if key not in ['lat', 'lng', 'date'] and \
                    data.get(key, None):
                additional[key] = data.get(key, None)
        return dict(location=location, recorded_at=recorded_at,
                    additional=additional)

    @classmethod
    def post(cls, request, sensor_type, provider_key):
        logger.info("Recieved new push message from {}: {}".format(sensor_type,
                    request.data))
        sensor_observations = request.data
        # Check if received data is in list format or not
        if isinstance(sensor_observations, dict):
            sensor_observations = [sensor_observations]
        errors = []
        for sensor_observation in sensor_observations:
            # Serialize sensor api data (one at a time), So that if there are
            # some errors, let's not discard whole payload and throw error
            params = FollowltObservation(data=sensor_observation)
            if not params.is_valid():
                errors.append(params.errors)
                continue
            try:
                data = cls.convert_to_das_format(params.data)
                src = Source.objects.ensure_source(
                    provider=provider_key,
                    manufacturer_id=params.data.get('collarId'))
                # Short-circuit if we already have this observation.
                if Observation.objects.filter(
                        source=src, recorded_at=data['recorded_at']).exists():
                    logger.info("Processed duplicate "
                                "observation: {}".format(data))
                    errors.append({})
                    continue
                data['source'] = str(src.id)
                serializer = ObservationSerializer(data=data)
                if serializer.is_valid():
                    serializer.save()
                    logger.info("Added new observation %s", data)
                    notify_new_tracks(src.id)
                    errors.append({})
                else:
                    errors.append(serializer.errors())
            except Exception as e:
                logger.error(str(e))
                errors.append(str(e))
        for error in errors:
            if error:
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({}, status=status.HTTP_201_CREATED)


class LocationDictSerializer(serializers.Serializer):
    lon = serializers.FloatField(min_value=-180.0, max_value=180.0)
    lat = serializers.FloatField(min_value=-90.0, max_value=90.0)


class RadioAdditionalSerializer(serializers.Serializer):
    event_action = serializers.CharField(max_length=40)
    radio_state = serializers.CharField(max_length=20)
    radio_state_at = serializers.DateTimeField()
    last_voice_call_start_at = serializers.DateTimeField(required=False)
    location_requested_at = serializers.DateTimeField(required=False)


class DraObservationSerializer(serializers.Serializer):

    manufacturer_id = serializers.CharField()
    source_type = serializers.CharField(default=None)
    subject_name = serializers.CharField(default=None)
    recorded_at = serializers.DateTimeField()
    location = LocationDictSerializer()

    subject_subtype = serializers.CharField(required=False, default='ranger')
    # model_name = serializers.CharField(default=None)
    additional = RadioAdditionalSerializer()


class DasRadioAgentHandler():
    '''
    Deprecated. I need to move das-radio-agent to the generic handler above.
    '''
    SENSOR_TYPE = 'dasradioagent'
    SOURCE_TYPE = 'gps-radio'
    DEFAULT_SUBJECT_SUBTYPE = 'ranger'

    @classmethod
    def handle_heartbeat(cls, data, provider_key):
        servicesutils.store_service_status(
            provider_key=provider_key, data=data)
        return Response(data, status=status.HTTP_200_OK)

    @classmethod
    def post(cls, request, provider_key):
        '''
        Handle Post from Das Radio Agent. The payload should have a 'message_key' to idenfity the type of
        status message.
        :param request:
        :param provider_key: The natural key found in SourceProvider.
        :return:
        '''
        data = request.data

        # Default to 'observation' for backward compatibility.
        key = data.get('message_key', 'observation')

        if key == 'heartbeat':
            return cls.handle_heartbeat(data, provider_key)

        if key == 'observation':
            return cls.handle_observation(data, provider_key)

    @classmethod
    def handle_observation(cls, data, provider_key):

        postdata = DraObservationSerializer(data=data)
        if not postdata.is_valid():
            return Response(data=postdata.errors, status=status.HTTP_400_BAD_REQUEST)
        postdata = postdata.validated_data

        location = {
            'longitude': postdata['location']['lon'],
            'latitude': postdata['location']['lat']
        }

        model_name = '{}:{}'.format(cls.SENSOR_TYPE, provider_key)
        manufacturer_id = postdata['manufacturer_id']

        src = Source.objects.ensure_source(source_type=cls.SOURCE_TYPE,
                                           provider=provider_key,
                                           manufacturer_id=manufacturer_id,
                                           model_name=model_name,
                                           subject={
                                               'subject_subtype_id': cls.DEFAULT_SUBJECT_SUBTYPE,
                                               'name': manufacturer_id
                                           }
                                           )

        recorded_at = postdata['recorded_at']

        event_action = data.get('additional', {}).get(
            'event_action', 'unknown')
        try:

            existing_observation = Observation.objects.get(
                source=src, recorded_at=recorded_at)

        except Observation.DoesNotExist:

            # Saving a new observation
            observation = {
                'location': location,
                'recorded_at': recorded_at,
                'source': str(src.id),
                'additional': data['additional'],
            }

            # Anything else that was included in the posted object should move into
            # additional.
            observation['additional'].update(
                dict((k, data[k]) for k in data if k not in observation.keys()))

            serializer = ObservationSerializer(data=observation)
            if serializer.is_valid():
                serializer.save()
                notify_new_tracks(src.id)
                logger.info("Adding new radio observation", extra={'radio.obs.new': provider_key,
                                                                   'radio.event_action': event_action})
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            logger.info("Processing new radio status", extra={'radio.status.update': provider_key,
                                                              'radio.event_action': event_action}
                        )

            update_subject_status_from_post(existing_observation.source, recorded_at=recorded_at,
                                            location=location, additional={'subject_name': postdata['subject_name'], **data['additional']})

        return Response({}, status=status.HTTP_200_OK)


class GsatHandler():
    SENSOR_TYPE = 'gsat'
    SOURCE_TYPE = 'gps-radio'
    DEFAULT_SUBJECT_SUBTYPE = 'ranger'

    @staticmethod
    def _parse_location(lat, lon):
        try:
            # return Point(x=float(lon), y=float(lat))
            return {'latitude': float(lat), 'longitude': float(lon)}
        except:
            raise

    @staticmethod
    def _parse_gsat_request(o):

        r = {}
        r['manufacturer_id'] = str(o.get('uniqueid'))
        r['location'] = GsatHandler._parse_location(o.get('lat'), o.get('lng'))
        r['recorded_at'] = GsatHandler._parse_gsat_timestamp(o)

        try:
            r['altitude_meters'] = float(o.get('alt'))
        except:
            pass

        try:
            r['speed_mps'] = float(o.get('speed'))
        except:
            pass

        try:
            r['heading'] = float(o.get('head'))
        except:
            pass

       # Calculate state, that will be recorded in SubjectStatus.
        r['state'] = 'alarm' if o.get('emer', 0) == '1' else 'default'

        r['events'] = o.get('events').split(',') if len(
            o.get('events', '')) > 0 else None

        r['sensor_type'] = GsatHandler.SENSOR_TYPE

        return r

    @staticmethod
    def _parse_gsat_timestamp(obj):
        try:
            return datetime.datetime.fromtimestamp(int(obj.get('time')), tz=pytz.UTC)
        except:
            return datetime.datetime.now(tz=pytz.UTC)

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

        if all(qp[k] == template[k] for k in qp if k in template) \
                and all(_ in qp for _ in GsatHandler.REQUIRED_PARAMS):
            return True

    @classmethod
    def post(cls, request, provider_key):

        logger.info('Gsat request: %s', request.query_params)

        try:
            obj = GsatHandler._parse_gsat_request(request.query_params)
        # except ValueError as ve:
        except Exception as e:
            if cls._validate_template_request(request.query_params):
                return Response({'data': 'That looks like a valid template request'})
            else:
                return Response({'data': 'Check query parameters and try again.'}, status=status.HTTP_400_BAD_REQUEST)

        obj['provider_key'] = provider_key

        model_name = '{}:{}'.format(GsatHandler.SENSOR_TYPE, provider_key)

        src, created = Source.objects.ensure_source(cls.SOURCE_TYPE,
                                                    provider=provider_key,
                                                    manufacturer_id=obj.get(
                                                        'manufacturer_id'),
                                                    model_name=model_name)

        # If the Source already exists, assume the SubjectSource and Subject
        # already exist.
        if created:
            ss, created = SubjectSource.objects.ensure_subject_source(src,
                                                                      timestamp=obj['recorded_at'],
                                                                      subject_subtype_id=cls.DEFAULT_SUBJECT_SUBTYPE
                                                                      )

        obj['additional'] = dict((k, obj[k]) for k in obj if k not in (
            'manufacturer_id', 'location', 'recorded_at',))
        obj['source'] = str(src.id)

        serializer = ObservationSerializer(data=obj)
        if serializer.is_valid():
            serializer.save()

            notify_new_tracks(src.id)
            logger.info("Processed duplicate %s observation",
                        cls.DEFAULT_SUBJECT_SUBTYPE, extra={'obs.new': provider_key})
            # GSAT service expects 200 and considers anything else bad.
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SkylineVehicleTrackerHandler():
    SENSOR_TYPE = 'vehicle-tracker-push'
    DEFAULT_SUBJECT_SUBTYPE = 'truck'

    @classmethod
    def post(cls, request, sensor_type, provider_key):

        logger.info("Recieved new push message %s", request.data,
                    extra={'msg.data': request.data})
        params = SkylineObservations(data=request.data)

        # short term don't throw away bad data, until
        # we understand what skyline is sending us
        if not params.is_valid():
            status_fail = {'status' : 105, 'message' : params.errors}
            return Response(data=status_fail, status=status.HTTP_400_BAD_REQUEST)

        adapter = SkylineAdapter()
        # TODO bulk_create
        # obs_to_insert = []

        for observation in params.data['Messages']:

            das_obs = adapter.create_das_object(observation)

            src = Source.objects.ensure_source(
                das_obs.source_type,
                provider=provider_key,
                manufacturer_id=das_obs.manufacturer_id,
                model_name=das_obs.model_name,
                subject={
                    'subject_subtype_id': das_obs.subject_subtype,
                    'name': das_obs.subject_name
                }
            )
            # skip if we already have this observation.
            if Observation.objects.filter(source=src, recorded_at=das_obs.recorded_at).exists():
                logger.info("Processed duplicate observation %s",
                            das_obs.subject_subtype, extra={'obs.dup': provider_key})
                continue

            observation = {
                'location': das_obs.location,
                'recorded_at': das_obs.recorded_at,
                'source': str(src.id),
                'additional': das_obs.additional,
            }

            serializer = ObservationSerializer(data=observation)
            if serializer.is_valid():
                serializer.save()
                logger.info("Added new observation %s", observation,
                            extra={'obs.new': provider_key})
                notify_new_tracks(src.id)
            else:
                logger.info("An error occured whle serializing the observation: %s", serializer.errors)
        status_ok = {'status' : 0, 'message' : 'success'}
        return Response(data=status_ok, status=status.HTTP_200_OK)


class TractVehicleHandler():

    SENSOR_TYPE = 'vehicle-observation'
    DEFAULT_SUBJECT_SUBTYPE = 'truck'

    @classmethod
    def post(cls, request, sensor_type, provider_key):

        logger.info("Recieved new push message %s", request.data)
        params = TractVehicleData.parse_observations(request.data)

        if not params.is_valid():
            status_fail = {'status' : 404, 'message' : params.errors}
            return Response(data=status_fail, status=status.HTTP_200_OK)

        else:
            adapter = TractAdapter()
            # need to 'unbind' these values
            mfg_id = params['MfgId'].value
            reg = params['Reg'].value

            for observation in params.data['Records']:
                das_obs = adapter.create_das_object(mfg_id, reg, observation)
                src = Source.objects.ensure_source(
                    das_obs.source_type,
                    provider=provider_key,
                    manufacturer_id=das_obs.manufacturer_id,
                    model_name=das_obs.model_name,
                    subject={
                        'subject_subtype_id': das_obs.subject_subtype,
                        'name': das_obs.subject_name
                    }
                )
                # skip if we already have this observation.
                if Observation.objects.filter(source=src, recorded_at=das_obs.recorded_at).exists():
                    logger.info("Processed duplicate observation %s",
                                das_obs.subject_subtype, extra={'obs.dup': provider_key})
                    continue

                observation = {
                    'location': das_obs.location,
                    'recorded_at': das_obs.recorded_at,
                    'source': str(src.id),
                    'additional': das_obs.additional,
                }

                serializer = ObservationSerializer(data=observation)
                if serializer.is_valid():
                    serializer.save()
                    logger.info("Added new observation %s", observation,
                                extra={'obs.new': provider_key})
                    notify_new_tracks(src.id)
                else:
                    logger.info("An error occured whle serializing the observation: %s", serializer.errors)

        
        status_ok = {'status' : 200, 'message' : 'success'}

        return Response(data=status_ok, status=status.HTTP_200_OK)
