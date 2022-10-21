import logging
import datetime

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework import serializers, views, permissions
import piexif
import dateutil.parser
import pytz

from activity.serializers import EventSerializer, EventFileSerializer
from usercontent.models import ImageFileContent
from activity.models import Event


logger = logging.getLogger(__name__)

default_time_zone = pytz.timezone(settings.SENSORS.get(
    'camera_trap', {}).get('default_time_zone', 'UTC'))


EXIF_FIELD_TO_REPORT = {
    'Model': 'cameratraprep_camera-name',
    'Make': 'cameratraprep_camera-make',
    'Software': 'cameratraprep_camera-version'
}

PARAMS_TO_REPORT = {
    'camera_name': 'cameratraprep_camera-name',
    'camera_description': 'cameratraprep_camera-make',
    'camera_version': 'cameratraprep_camera-version'
}


def get_priority():
    """The priority for an event. For now uses a default of Red"""
    return settings.SENSORS.get(
        'camera_trap', {}).get('priority', Event.PRI_URGENT)


def exif_dateparse(date_str, default_tz=pytz.utc):
    """Exif date format is YYYY:MM:DD HH:MM:SS"""
    dt = datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=default_tz)
    return dt


def exif_time_zone(timezone_str):
    """example exif timezone string -04:00 """
    hrs, mins = timezone_str.split(':')
    hrs = abs(int(hrs))
    mins = int(mins)
    mins = hrs * 60 + mins
    if timezone_str.startswith('-'):
        mins = mins * -1
    return pytz.FixedOffset(mins)


def dateparse(date_str, default_tz=pytz.utc):
    dt = dateutil.parser.parse(date_str)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=default_tz)
    return dt


class CameraTrapPostParameters(serializers.Serializer):
    location = serializers.JSONField(default=None)
    file = serializers.FileField()
    camera_name = serializers.CharField(default=None)
    time = serializers.DateTimeField(default=None)
    camera_description = serializers.CharField(default=None)
    camera_version = serializers.CharField(default=None)
    group_id = serializers.UUIDField(default=None)


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
    gps_exif = {piexif.TAGS[GPS_EXIF_NAME][tag]["name"]                : exif[GPS_EXIF_NAME][tag] for tag in exif[GPS_EXIF_NAME]}
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
    serializer_class = CameraTrapPostParameters

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
        # for now, just return a 400 (should be a 415) if the extension is '.png'
        # later, we'll get a bit more clever, and refactor the code so that a 
        # user can pass in valid data with a png. 
        if '.png' in file_name.lower():
            return Response(data='png is not a supported media type',
                                status=status.HTTP_400_BAD_REQUEST)
        exif = load_exif(file.read())
        exif_dict = dict(iter_exif(exif))
        location = None

        if params.validated_data['camera_name']:
            camera_name = params.validated_data['camera_name']
        else:
            camera_name = exif_dict['Model'].decode('utf-8') if exif_dict.get('Model') else \
                None

        title = '{camera_name} detection'.format(camera_name=camera_name)

        if params.validated_data['location']:
            location = params.validated_data['location']
        else:
            try:
                location = get_lat_lon(exif)
            except KeyError:
                logger.exception('Corrupt GPS info in file: %s', camera_name)

        if cls.if_exists_event_file(file_name):
            return Response(status=status.HTTP_409_CONFLICT)

        if params.validated_data['group_id']:
            try:
                event = Event.objects.get(id=params.validated_data['group_id'])
            except Event.DoesNotExist:
                message = 'Group with id {group_id} for image not found'.format(
                    params.validated_data['group_id'])
                return Response(status=status.HTTP_404_NOT_FOUND,
                                data={'message': message})
        else:
            if params.validated_data['time']:
                event_time = params.validated_data['time']
            else:
                event_time = cls.get_time(params, exif_dict)

            event_details = cls.get_camera_trap_details(params, exif_dict)
            event_data = dict(title=title,
                              event_type='cameratrap_rep',
                              event_details=event_details,
                              priority=get_priority(),
                              )

            if location:
                event_data['location'] = location

            if event_time:
                event_data['time'] = event_time

            eser = EventSerializer(data=event_data, context={
                                   'request': request})
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

        return Response({'group_id': str(event.id)},
                        status=status.HTTP_201_CREATED)

    @classmethod
    def if_exists_event_file(cls, filename):
        for image in ImageFileContent.objects.all().filter(filename=filename):
            return True
        return False

    @classmethod
    def get_camera_trap_details(cls, params, exif_dict):
        result = {'cameratraprep_camera-name': params.validated_data['camera_name'],
                  }

        for exif_field, report_field in EXIF_FIELD_TO_REPORT.items():
            if exif_field in exif_dict:
                result[report_field] = exif_dict[exif_field].decode('utf-8')

        for field, report_field in PARAMS_TO_REPORT.items():
            if params.validated_data.get(field, None):
                result[report_field] = params.validated_data.get(field)

        return result

    @classmethod
    def get_time(cls, params, exif_dict):
        try:
            event_time = exif_dict['DateTimeOriginal'].decode('utf-8')
            timezone = default_time_zone
            if 'OffsetTimeOriginal' in exif_dict:
                timezone = exif_time_zone(
                    exif_dict['OffsetTimeOriginal'].decode('utf-8'))
            event_time = exif_dateparse(event_time, timezone)

        except KeyError:
            event_time = params.validated_data['time']
        return event_time


class PantheraCameraTrapSensorHandler(CameraTrapSensorHandler):
    SENSOR_TYPE = 'camera-trap'
    PROVIDER_NAME = 'panthera'
