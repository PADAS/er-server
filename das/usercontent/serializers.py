import logging

from django.core.urlresolvers import reverse
import rest_framework.serializers
import utils

import usercontent.models

logger = logging.getLogger(__name__)

class FileContentSerializer(rest_framework.serializers.ModelSerializer):
    # added_by = rest_framework.serializers.HiddenField(
    #     default=rest_framework.serializers.CurrentUserDefault()
    # )
    #
    # file = rest_framework.serializers.FileField()
    #
    class Meta:
        model = usercontent.models.FileContent

    # def to_representation(self, content):
    #     rep = super().to_representation(content)
    #
    #     if 'request' in self.context:
    #         rep['url'] = utils.add_base_url(self.context['request'],
    #                                     reverse('file-content-view',
    #                                             args=[str(content.id),]))
    #
    #     return rep

