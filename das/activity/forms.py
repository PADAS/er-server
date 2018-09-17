import os

from django.contrib.staticfiles.storage import staticfiles_storage

from django import forms
from django.forms.widgets import Widget
from django.utils.translation import ugettext_lazy as _

import logging
logger = logging.getLogger(__name__)

from core.forms_utils import JSONFieldFormMixin

from activity.models import EventProvider


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


class IconKeyInput(Widget):
    input_type = 'text'
    template_name = 'admin/activity/eventtype/icon_key_widget.html'

    def __init__(self, attrs=None, image_list_fn=None):
        if attrs is not None:
            attrs = attrs.copy()
            self.input_type = attrs.pop('type', self.input_type)
        self.image_list_fn = image_list_fn
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['type'] = self.input_type
        image_list = list(self.image_list_fn())
        context['image_list'] = image_list

        if context['widget']['value']:
            try:
                context['widget']['file_path'] = \
                    next(o for o in image_list if o['key'] == context['widget']['value'])[
                    'file_path']
            except StopIteration:
                pass

        return context

    class Media:
        css = {
            'all': ('css/icon_key_text.css',),
        }


def get_event_icon_select_list(dirname='sprite-src'):
    icon_list = [
        {
            'key': item.split('.')[0],
            'file_path': staticfiles_storage.url(os.sep.join((dirname, item)))
        }
        for item in staticfiles_storage.listdir(dirname)[1]
    ]
    return icon_list


class EventTypeForm(forms.ModelForm):
    schema = forms.CharField(widget=SchemaWidget(
        attrs={'rows': 30, 'cols': 100}))

    icon = forms.CharField(required=False,
                           label='Icon Override',
                           widget=IconKeyInput(image_list_fn=get_event_icon_select_list))


from django.forms import TextInput


class EventProviderForm(JSONFieldFormMixin, forms.ModelForm):

    provider_api = forms.URLField(label='Provider API', required=True, widget=TextInput(attrs={'size': '100'}),
                                  help_text=_('A URL or web service endpoint for the external data source.'))
    provider_username = forms.CharField(label='Provider API Username', required=False,
                                        help_text=_('If the external data source requires a username, enter it here.'))
    provider_password = forms.CharField(label='Provider API Password', required=False,
                                        help_text=_('If the external data source requires a password, enter it here.'))
    provider_token = forms.CharField(label='Provider Authorization Token', widget=TextInput(attrs={'size': '100'}),
                                     required=False,
                                     help_text=_('If you were given an authorization token for the external data source, enter it here.'))

    class Meta:
        model = EventProvider
        json_fields = ('provider_api', 'provider_username',
                       'provider_password', 'provider_token')
        fields = ('additional',) + json_fields
