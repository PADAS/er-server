from django.conf import settings
from datetime import datetime, timedelta
import pytz
from dateutil.parser import parse

from django.utils.safestring import mark_safe
from django import forms
from django.forms.fields import MultiValueField, DateTimeField
from django.forms import MultiWidget

from django.forms.widgets import DateTimeInput, TextInput, Widget


class ColorPickerWidget(TextInput):
    '''
    This widget works closely with a customized version of bootstrap-colorpicker.
    '''
    class Media:
        css = {
            'all': (
                '{}css/bootstrap-colorpicker.css'.format(settings.STATIC_URL),
            )
        }
        js = (
            '//code.jquery.com/jquery-3.2.1.js',
            '{}js/bootstrap-colorpicker.js'.format(settings.STATIC_URL),
        )

    def __init__(self, language=None, attrs=None):
        self.language = language or settings.LANGUAGE_CODE[:2]
        super(ColorPickerWidget, self).__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        rendered = super(ColorPickerWidget, self).render(
            name, value, attrs, renderer)
        return rendered + mark_safe(
            '''<script type="text/javascript">
            $('#id_%s').colorpicker({format: 'rawrgb'});
            </script>''' % (name,)
        )


class JSONFieldFormMixin(object):
    '''
    This mixin can be used in a Form where we want to provide individual form elements for a set of keys
    within a Model's Json field identified by 'json_field'.
    '''
    json_field = "additional"

    def get_json(self):
        return getattr(self.instance, self.json_field)

    def __init__(self, *args, **kwargs):
        super(JSONFieldFormMixin, self).__init__(*args, **kwargs)

        if self.instance:
            json_data = self.get_json()
            # Check json_field's value type to avoid parsing error
            if json_data and isinstance(json_data, dict):
                for field in self.Meta.json_fields:

                    if json_data.get(field) is not None:
                        try:
                            if field in getattr(self.Meta, 'json_date_fields', set()):
                                initial_value = self.fields[field].initial = parse(
                                    json_data.get(field))
                            else:
                                initial_value = json_data.get(field)
                        except Exception:
                            initial_value = json_data.get(field)

                        self.fields[field].initial = initial_value

    def save(self, *args, **kwargs):
        json_data = self.get_json()
        # If json_field's value type is not dict, than assign empty dictionary
        if not isinstance(json_data, dict):
            json_data = {}
        for field in self.Meta.json_fields:
            json_data[field] = self.cleaned_data[field]
            if isinstance(self.cleaned_data[field], datetime):
                utc_date = self.cleaned_data[field].astimezone(
                    pytz.timezone('UTC'))
                json_data[field] = utc_date.isoformat()
        setattr(self.instance, self.json_field, json_data)
        return super(JSONFieldFormMixin, self).save(*args, **kwargs)


class AssignedDateTimeRangeWidget(MultiWidget):

    def __init__(self):
        widgets = (
            DateTimeInput(format='%Y-%m-%d %H:%M:%S%z', attrs={'size': '30'}),
            DateTimeInput(format='%Y-%m-%d %H:%M:%S%z', attrs={'size': '30'}),
        )
        super().__init__(widgets)

    def decompress(self, value):
        if value:
            return [value.lower, value.upper]
        return [None, None]


datetime_formats = ('%Y-%m-%d %H:%M:%S%z',
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M',
                    '%Y-%m-%d',
                    )


class AssignedDateTimeRangeField(MultiValueField):
    def __init__(self, **kwargs):
        # TODO: Define error messsage for field group.
        error_messages = {
            'incomplete': 'Assigned start and end dates must be valid date-time values.',
        }
        # TODO: Define an error message for each field.
        fields = (
            DateTimeField(input_formats=datetime_formats, required=False),
            DateTimeField(input_formats=datetime_formats, required=False),
        )

        super().__init__(
            error_messages=error_messages, fields=fields,
            require_all_fields=False,
            widget=AssignedDateTimeRangeWidget(), **kwargs
        )

    def compress(self, data_list):
        print(data_list)
        (d1, d2) = data_list
        if d1 is None:
            d1 = datetime.min.replace(tzinfo=pytz.utc)
        if d2 is None:
            d2 = datetime.max.replace(tzinfo=pytz.utc)
        return (d1, d2)


class FixedWidthFontTextArea(forms.Textarea):
    template_name = 'admin/core/fixed_width_textarea.html'

    def __init__(self, attrs=None):
        # Use slightly better defaults than HTML's 20x2 box
        default_attrs = {'cols': '50', 'rows': '40'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    class Media:
        css = {
            'all': ('css/fixed_width_textarea.css',),
        }
