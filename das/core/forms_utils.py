from django.conf import settings
from datetime import datetime, timedelta
import pytz
from dateutil.parser import parse

from django.utils.safestring import mark_safe
from django.forms.fields import MultiValueField, DateTimeField
from django.forms import MultiWidget

from django.forms.widgets import DateTimeInput, TextInput


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

    def render(self, name, value, attrs=None):
        rendered = super(ColorPickerWidget, self).render(name, value, attrs)
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
            for field in self.Meta.json_fields:
                if json_data.get(field):
                    try:
                        self.fields[field].initial = parse(json_data.get(field))
                    except Exception as e:
                        self.fields[field].initial = json_data.get(field)

    def save(self, *args, **kwargs):
        json_data = self.get_json()
        for field in self.Meta.json_fields:
            json_data[field] = self.cleaned_data[field]
            if isinstance(self.cleaned_data[field], datetime):
                # If timezone is there, Replace with UTC or else put it there
                if self.cleaned_data[field].tzinfo:
                    utc_date = self.cleaned_data[field].astimezone(
                        pytz.timezone('UTC'))
                else:
                    utc_date = pytz.utc.localize(self.cleaned_data[field])
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
