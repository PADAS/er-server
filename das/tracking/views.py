from datetime import timedelta

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from oauth2_provider.ext.rest_framework import OAuth2Authentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from dateutil.parser import parse as parse_date
import pytz
from django.contrib.gis.geos import Point
from django.db import transaction

from observations.models import Observation, Source, SubjectSource, Subject
from observations.serializers import ObservationSerializer
from activity.models import Event, EventAttachment
from activity.serializers import EventSerializer


def __str2date(d, default_tzinfo=pytz.UTC):
    '''Parse a date and if it's naive, replace tzinfo with default_tzinfo.'''
    dt = parse_date(d)
    if not dt.tzinfo:
        return dt.replace(tzinfo=default_tzinfo)
    return dt


@api_view(['POST', 'GET'])
@authentication_classes((OAuth2Authentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def observation_list(request):
    """
    For a manufacturer_id:
        list some observations, or create a new observation.
    """
    if request.method == 'POST':

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

        src, created = Source.objects.get_or_create(source_type=source_type,
                                           manufacturer_id=manufacturer_id,
                                           defaults={'model_name':'auto-created',
                                                     'additional': {'note':'automatically created during observation post.'}})

        recorded_at = request.data.get('recorded_at')
        # if recorded_at:
        #     recorded_at = parser.parse(recorded_at)

        observation_data = {
            'location': location,
            'recorded_at': recorded_at,
            'source': src.id,
            'additional': request.data.get('additional', {"note":"default"}),
        }


        serializer = ObservationSerializer(data=observation_data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'GET':

        manufacturer_id = request.query_params.get('manufacturer_id')
        source_type = request.query_params.get('source_type', 'gps-radio')
        if manufacturer_id:
            src = Source.objects.filter(source_type=source_type, manufacturer_id=manufacturer_id).first()

            if src:

                o = Observation.objects.filter(source=src)[:5]
                serializer = ObservationSerializer(o, many=True)
                return Response(serializer.data)

        return Response(status=status.HTTP_404_NOT_FOUND)

@api_view(['POST','GET'])
@authentication_classes((OAuth2Authentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def message_list(request):
    """
    Messages API for posting text messages for a particular source (ex. mototrbo radio).
    """
    if request.method == 'POST':

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

        recorded_at = __str2date(recorded_at)

        src = ensure_source(source_type, manufacturer_id)
        ss = ensure_subject_source(src, recorded_at)

        message_name = 'Message from {}'.format(ss.subject.name)
        message_body = request.data.get('message_body')

        with transaction.atomic():
            event = Event(
                event_type=Event.ET_RADIO_TEXT_MESSAGE,
                provenance=Event.SYSTEM,
                attributes={},
                location=location,
                priority=Event.PRI_IMPORTANT,
                name=message_name,
                description=message_body
            )

            event.save()

            # TODO: For now, use reason=target, to let the UI treat this as it does analyzer events.
            event_attachment = EventAttachment(event=event, target=ss.subject, reason=EventAttachment.TARGET)
            event_attachment.save()

        serializer = EventSerializer(event)
        return Response({'event_id':str(event.id)}, status=status.HTTP_201_CREATED)
    elif request.method == 'GET':
        return Response({}, status=status.HTTP_200_OK)


# Helper functions for hydrating Source and Subject for the given message.
def ensure_source(source_type, manufacturer_id):
    src, created = Source.objects.get_or_create(source_type=source_type,
                                   manufacturer_id=manufacturer_id,
                                   defaults={'model_name':'auto-created',
                                             'additional': {'note': 'automatically created during message post.'}})

    return src


def ensure_subject_source(source, event_time):
    # get the most recent Subject for this Source
    subject_source = SubjectSource \
                        .objects \
                        .filter(source=source, assigned_range__contains=event_time)\
                        .order_by('assigned_range')\
                        .reverse()\
                        .first()

    if not subject_source:

        sub, created = Subject.objects.get_or_create(
            subject_type='person', subject_subtype='ranger',
            name=source.manufacturer_id,
            defaults=dict(additional=dict(region='', country='', ))
        )

        d1 = event_time
        d2 = d1 + timedelta(days=365)
        if sub:
            subject_source, created = SubjectSource.objects.get_or_create(source=source, subject=sub,
                                                                 defaults=dict(assigned_range=(d1, d2), additional={
                                                                     'note': 'Automatically created as part of message post.'}))

    return subject_source
