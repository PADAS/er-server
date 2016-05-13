from django.contrib.gis.geos import Point
from django.core.urlresolvers import reverse

import rest_framework.serializers
from rest_framework.fields import DateTimeField, CharField
from drf_extra_fields.geo_fields import PointField

import utils
import activity.models
from observations.serializers import SubjectSerializer, SourceSerializer
from activity.manager import AC_DELETED, AC_UPDATED
from accounts.serializers import UserDisplaySerializer


ATTACHMENT_SERIALIZER_MAPPING = {
    'observations.subject': {'serializer': SubjectSerializer,
                             'field': 'subject'},
    'observations.source': {'serializer': SourceSerializer,
                            'field': 'source'},
}


class EventAttachmentSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = activity.models.EventAttachment


class EventSerializer(rest_framework.serializers.ModelSerializer):
    # Using PointField here provides the magic to convert between a
    #  json {lat/lon} and our internal representation.
    location = PointField(required=False)
    time = DateTimeField(source='event_time')
    class Meta:
        model = activity.models.Event
        fields = (
            'id', 'location', 'time', 'message', 'provenance',
            'event_type', 'priority', 'priority_label', 'attributes',
            'image_url')
        id_field = False
        geo_field = 'location'

    def create(self, validated_data):
        return activity.models.Event.objects.create_event(**validated_data)

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance

    def to_representation(self, event):
        rep = super().to_representation(event)
        rep['url'] = utils.add_base_url(self.context['request'],
                                            reverse('event-view',
                                                    args=[event.id, ]))

        if event.location is not None:
            geodata = make_feature(self.context['request'], event)
            rep['geojson'] = geodata

        subject_attachment = event.attachments.filter(reason='target')

        if subject_attachment:
            try:
                # TODO: Fix this so it can handle different types of attachments.
                subject_attachment = subject_attachment[0]
                rep['subject'] = SubjectSerializer().to_representation(subject_attachment.target)
            except:
                pass

        rep['updates'] = self.render_updates(event)
        return rep

    def render_updates(self, event):
        def get_username(user):
            if not user:
                return ''
            if not user.get_full_name():
                return user.get_username()
            return user.get_full_name()

        def get_action(revision):
            if revision.action == AC_UPDATED:
                field_mapping = {'message': 'Event Text',
                                 'event_time': 'Event Time',
                                 'priority': 'Event Priority',
                                 'location': 'Location',
                                 'provenance': 'Event Reporter',
                                 'created_by_user': 'Event Writer'}
                fieldnames = [field_mapping[k] for k in revision.data.keys() if k in field_mapping]
                '{0} fields: {1}'.format(revision.get_action_display(),
                                         ', '.join(fieldnames))
            return revision.get_action_display()

        return [dict(message='Event {action} by {user}'.format(
            action=get_action(revision),
            user=get_username(revision.user)
        ), time=revision.revision_at.isoformat(),
           user=UserDisplaySerializer().to_representation(revision.user))
                for revision in event.get_history()
                ]

def make_feature(request, event):
    is_point = isinstance(event.coordinates, Point)
    image_url = utils.add_base_url(request, event.image_url)
    feature = utils.json.empty_geojson_feature()
    feature['geometry'] = {
        'type': 'LineString' if not is_point else 'Point',
        'coordinates': event.coordinates if not is_point else event.coordinates.tuple
    }
    feature['type'] = 'Feature'
    feature['properties'] = {
        'message': event.message,
        'datetime': event.time,
        'image': event.image_url
    }

    properties = feature['properties']
    if hasattr(event, 'image_url'):

        properties['icon'] = {
            "iconUrl": image_url,
            "iconSize": [25, 25],
            "iconAncor": [12, 12],
            "popupAncor": [0, -13],
            "className": 'dot',

        }
        # feature['style'] = {
        #     "color": event.color,
        #     "opacity": 1,
        #     "deprecating": "use https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0"
        # }
        # # see https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0
        # properties['stroke'] = event.color
        # properties['stroke-opacity'] = 1.0
        # properties['stroke-width'] = 2
        # properties['icon'] = image_url

    return feature
