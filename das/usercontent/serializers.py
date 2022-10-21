import logging

from django.conf import settings
import rest_framework.serializers
import utils
from core.utils import static_image_finder
from versatileimagefield.serializers import VersatileImageFieldSerializer

import usercontent.models

logger = logging.getLogger(__name__)

DEFAULT_FILE_ICON = '/static/icon-txt.png'

# Load UserContent settings once from settings.
USERCONTENT_SETTINGS = getattr(settings, 'USERCONTENT_SETTINGS', {})
IMAGEFILE_EXTENSIONS = USERCONTENT_SETTINGS.get('imagefile_extensions', set())

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
    file_type = rest_framework.serializers.SerializerMethodField()

    class Meta:
        model = usercontent.models.FileContent
        read_only_fields = ('created_at', 'updated_at', 'created_by')
        fields = ('id', 'file', 'filename', 'icon_url', 'file_type') + read_only_fields

    def get_file_type(self, instance):
        '''Static file_type that a client can rely on.'''
        return 'file'

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
    file_type = rest_framework.serializers.SerializerMethodField()

    class Meta:
        model = usercontent.models.ImageFileContent
        read_only_fields = ('created_at', 'updated_at','created_by',)
        fields = ('id', 'file', 'filename', 'icon_url', 'file_type') + read_only_fields

    def get_file_type(self, instance):
        '''Static file_type that a client can rely on.'''
        return 'image'

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

    # image_url = rest_framework.serializers.SerializerMethodField()
    #
    # def get_image_url(self, filecontent):
    #     image_url = resolve_file_icon(filecontent)
    #     return utils.add_base_url(self.context['request'], image_url)

    def to_representation(self, instance):

        if isinstance(instance, usercontent.models.FileContent):
            content_serializer = FileContentSerializer(context={'request': self.context['request']})
        elif isinstance(instance, usercontent.models.ImageFileContent):
            content_serializer = ImageFileContentSerializer(context={'request': self.context['request']})

        rep = content_serializer.to_representation(instance)
        return rep

    def create(self, validated_data):

        if validated_data['file'].name.split('.')[-1].lower() in IMAGEFILE_EXTENSIONS:
            ser = ImageFileContentSerializer()
        else:
            ser = FileContentSerializer()

        instance = ser.create(validated_data)

        return instance


def get_available_renditions(sizes=None):
    if not sizes:
        return {}
    renditions = VersatileImageFieldSerializer(sizes=sizes).sizes
    renditions = dict(renditions)
    return renditions


IMAGE_RENDITIONS = {'default': get_available_renditions(sizes='default')}


def get_stored_filename(file, rendition_set='default', rendition_key=None):
    '''
    VersatileImageFieldSerializer knows how to get the renditions, so
    we can defer to it to determine which files are available for an image.
    '''
    try:
        renditions = IMAGE_RENDITIONS[rendition_set]
        rendition = renditions.get(rendition_key, 'None')
        rendition_type, key = rendition.split('__')

        # We can expect to see rendition_type in (thumbnail, crop)
        if hasattr(file, rendition_type):
            return getattr(file, rendition_type)[key].name

    except ValueError:
        pass

    return file.name
