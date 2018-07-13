from django.utils.translation import ugettext_lazy as _

from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.widgets import FilteredSelectMultiple

from observations.models import Subject, Source, SubjectGroup, SubjectSource, SubjectSubType
from observations.forms_utils import JSONFieldFormMixin, ColorPickerWidget, AssignedDateTimeRangeField

import logging
logger = logging.getLogger(__name__)


class SchemaWidget(forms.Textarea):
    template_name = 'admin/activity/eventtype/schema_textarea.html'

    def __init__(self, attrs=None):
        # Use slightly better defaults than HTML's 20x2 box
        default_attrs = {'cols': '50', 'rows': '100'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    class Media:
        css = {
            'all': ('css/schema_textarea.css',),
        }


class EventTypeForm(forms.ModelForm):
    schema = forms.CharField(widget=SchemaWidget(
        attrs={'rows': 30, 'cols': 100}))
