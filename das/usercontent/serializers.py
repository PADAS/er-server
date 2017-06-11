import logging

from django.conf import settings
import rest_framework.serializers
import utils
from core.utils import static_image_finder
from versatileimagefield.serializers import VersatileImageFieldSerializer

import usercontent.models

logger = logging.getLogger(__name__)

DEFAULT_FILE_ICON = '/static/icon-txt.png'

def resolve_file_icon(filecontent):
    try:
        image_key = 'icon-{}'.format(filecontent.filename.split('.')[-1])
    except:
        image_key = None
    return static_image_finder.get_marker_icon([image_key, ]) or DEFAULT_FILE_ICON



class FileContentSerializer(rest_framework.serializers.ModelSerializer):

    created_by = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )

    icon_url = rest_framework.serializers.SerializerMethodField()

    class Meta:
        model = usercontent.models.FileContent

    def get_icon_url(self, filecontent):
        return utils.add_base_url(self.context['request'], resolve_file_icon(filecontent))

    def to_representation(self, instance):

        rep = super().to_representation(instance)
        del rep['file']
        return rep


class ImageFileContentSerializer(rest_framework.serializers.ModelSerializer):


    created_by = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )

    icon_url = rest_framework.serializers.SerializerMethodField()

    image_urls = VersatileImageFieldSerializer(sizes='event_photo', source='file')

    class Meta:
        model = usercontent.models.ImageFileContent

    def get_icon_url(self, filecontent):
        return utils.add_base_url(self.context['request'], resolve_file_icon(filecontent))

    def to_representation(self, instance):

        rep = super().to_representation(instance)
        del rep['file']
        return rep


class UserContentSerializer(rest_framework.serializers.Serializer):

    created_by = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )

    file = rest_framework.serializers.FileField()
    filename = rest_framework.serializers.CharField(label='Name of uploaded file.', required=False)

    image_url = rest_framework.serializers.SerializerMethodField()

    def get_image_url(self, filecontent):
        image_url = resolve_file_icon(filecontent)
        return utils.add_base_url(self.context['request'], image_url)

    def to_representation(self, instance):

        if isinstance(instance, usercontent.models.FileContent):
            content_serializer = FileContentSerializer(context={'request': self.context['request']})
        elif isinstance(instance, usercontent.models.ImageFileContent):
            content_serializer = ImageFileContentSerializer(context={'request': self.context['request']})

        rep = content_serializer.to_representation(instance)
        return rep

    def create(self, validated_data):

        imagefile_extensions = getattr(settings, 'USERCONTENT', {}).get('imagefile_extensions', set())
        if validated_data['file'].name.split('.')[-1].lower() in imagefile_extensions:
            ser = ImageFileContentSerializer()
        else:
            ser = FileContentSerializer()

        instance = ser.create(validated_data)

        return instance
