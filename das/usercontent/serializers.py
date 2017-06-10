import logging

import rest_framework.serializers
import utils
from core.utils import static_image_finder

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

    image_url = rest_framework.serializers.SerializerMethodField()

    class Meta:
        model = usercontent.models.FileContent

    def get_image_url(self, filecontent):
        image_url = resolve_file_icon(filecontent)
        return utils.add_base_url(self.context['request'], image_url)

    def to_representation(self, instance):

        rep = super().to_representation(instance)
        del rep['file']
        return rep