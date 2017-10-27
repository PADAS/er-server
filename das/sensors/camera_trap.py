import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework import serializers, views, permissions
import piexif
import dateutil.parser
import pytz

from utils import json
from activity.serializers import EventSerializer, EventFileSerializer
from usercontent.models import ImageFileContent
from activity.models import Event


logger = logging.getLogger(__name__)


def get_priority():
    """The priority for an event. For now uses a default of Red"""
    return Event.PRI_URGENT


def dateparse(date_str, default_tz=pytz.utc):
    dt = dateutil.parser.parse(date_str)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=default_tz)
    return dt


class CameraTrapPostParameters(serializers.Serializer):
    location = serializers.DictField(default=None)
    file = serializers.FileField()
    camera_name = serializers.CharField(default=None)
    event_time = serializers.DateTimeField(default=None)


GPS_EXIF_NAME = 'GPS'


def get_float(x): return float(x[0]) / float(x[1])


def convert_to_degrees(value):
    d = get_float(value[0])
    m = get_float(value[1])
    s = get_float(value[2])
    return d + (m / 60.0) + (s / 3600.0)


def get_lat_lon(exif):
    if GPS_EXIF_NAME not in exif:
        return
    gps_exif = {piexif.TAGS[GPS_EXIF_NAME][tag]["name"]
        : exif[GPS_EXIF_NAME][tag] for tag in exif[GPS_EXIF_NAME]}
    gps_latitude = gps_exif['GPSLatitude']
    gps_latitude_ref = gps_exif['GPSLatitudeRef']
    gps_longitude = gps_exif['GPSLongitude']
    gps_longitude_ref = gps_exif['GPSLongitudeRef']
    lat = convert_to_degrees(gps_latitude)
    if gps_latitude_ref and gps_latitude_ref.decode('utf-8') != "N":
        lat *= -1

    lon = convert_to_degrees(gps_longitude)
    if gps_longitude_ref and gps_longitude_ref.decode('utf-8') != "E":
        lon *= -1
    return {'latitude': lat, 'longitude': lon}


def load_exif(file):
    return piexif.load(file)


def iter_exif(exif_dict):
    for ifd in ("0th", "Exif", "GPS", "1st"):
        for tag in exif_dict[ifd]:
            yield piexif.TAGS[ifd][tag]["name"], exif_dict[ifd][tag]


class CameraTrapSensorHandler:
    SENSOR_TYPE = 'camera-trap'

    @classmethod
    def post(cls, request, provider_name):
        # TODO: This conditional is to handle the case where a file is uploaded
        # via XHR. Figure out why.
        if 'filecontent.file' not in request.data:
            try:
                # Ajax request.
                request.data['filecontent.file'] = request.stream.FILES[
                    'filecontent.file']
            except KeyError:
                pass

        request.data['file'] = request.data['filecontent.file']
        params = CameraTrapPostParameters(data=request.data)
        if not params.is_valid():
            return Response(data=params.errors,
                            status=status.HTTP_400_BAD_REQUEST)

        if provider_name == PantheraCameraTrapSensorHandler.PROVIDER_NAME:
            cls = PantheraCameraTrapSensorHandler

        return cls.post_camera_trap_report(request, params)

    @classmethod
    def post_camera_trap_report(cls, request, params):
        file = request.data['filecontent.file']
        file_name = file.name
        exif = load_exif(file.read())
        exif_dict = dict(iter_exif(exif))

        camera_name = exif_dict['Model'].decode('utf-8') if exif_dict.get('Model') else \
            params.validated_data['camera_name']

        title = '{camera_name} detection'.format(camera_name=camera_name)

        location = params.validated_data['location'] if params.validated_data['location'] else None
        try:
            location = get_lat_lon(exif)
        except KeyError:
            logger.exception('Corrupt GPS info in file: %s', camera_name)

        if cls.if_exists_event_file(file_name):
            return Response(status=status.HTTP_409_CONFLICT)

        try:
            event_time = dateparse(exif_dict['DateTimeOriginal'])
        except KeyError:
            event_time = params.validated_data['event_time']

        event_details = cls.get_camera_trap_details(params, exif_dict)
        event_data = dict(title=title, location=location,
                          time=event_time,
                          event_type='cameratrap_rep',
                          event_details=event_details,
                          priority=get_priority(),
                          )

        eser = EventSerializer(data=event_data, context={'request': request})
        if not eser.is_valid():
            return Response(data=eser.errors,
                            status=status.HTTP_400_BAD_REQUEST)
        event = eser.create(eser.validated_data)

        event_file_ser = EventFileSerializer(data={'event': event.id,
                                                   'file': file},
                                             context={'request': request})
        if not event_file_ser.is_valid():
            return Response(data=event_file_ser.errors,
                            status=status.HTTP_400_BAD_REQUEST)
        event_file = event_file_ser.create(event_file_ser.validated_data)

        return Response({}, status=status.HTTP_201_CREATED)

    @classmethod
    def if_exists_event_file(cls, filename):
        for image in ImageFileContent.objects.all().filter(filename=filename):
            return True
        return False

    @classmethod
    def get_camera_trap_details(cls, params, exif_dict):
        result = {'cameratraprep_camera-name': params.validated_data['camera_name'],
                  }

        return result


class PantheraCameraTrapSensorHandler(CameraTrapSensorHandler):
    SENSOR_TYPE = 'camera-trap'
    PROVIDER_NAME = 'panthera'

    @classmethod
    def get_camera_trap_details(cls, params, exif_dict):
        result = {'cameratraprep_camera-name': exif_dict['Model'].decode('utf-8'),
                  'cameratraprep_camera-make': exif_dict['Make'].decode('utf-8'),
                  'cameratraprep_camera-version': exif_dict['Software'].decode('utf-8')}

        return result
