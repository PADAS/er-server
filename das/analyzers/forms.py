import re

from django.utils.translation import ugettext_lazy as _

from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.widgets import FilteredSelectMultiple, AdminDateWidget

from analyzers.environmental import EnvironmentalSubjectAnalyzerConfig
from core.forms_utils import JSONFieldFormMixin, FixedWidthFontTextArea


import logging
logger = logging.getLogger(__name__)


class EnvironmentalAnalyzerAdminForm(JSONFieldFormMixin, forms.ModelForm):

    earth_engine_json_key = forms.CharField(label='Earth Engine JSON Key',
                                            widget=FixedWidthFontTextArea(),
                                     required=False,
                                     help_text=_(
                                         'Paste the contents of your Earth Engine JSON key here.'))

    class Meta:
        model = EnvironmentalSubjectAnalyzerConfig
        json_fields = ('earth_engine_json_key',)
        fields = ('additional',) + json_fields
