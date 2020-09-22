import jsonschema
from rest_framework import serializers
from rest_framework.fields import empty, DateTimeField
from rest_framework.utils import html
from drf_extra_fields.compat import DateTimeTZRange
from drf_extra_fields.fields import RangeField


class CoordinateField(serializers.Field):
    allow_null = True
    schema = {
        "type": "object",
        "properties": {
            "latitude": {
                "type": "number"
            },
            "longitude": {
                "type": "number"
            }
        }
    }

    @classmethod
    def validate(cls, data):
        try:
            jsonschema.validate(instance=data, schema=cls.schema)
        except jsonschema.exceptions.ValidationError as ex:
            raise serializers.ValidationError(ex.message)

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        self.validate(data)

        return data


def choicefield_serializer(choices, default=empty, **kwargs):
    return serializers.ChoiceField(choices=choices, default=default, **kwargs)


def text_field(**kwargs):
    style = kwargs.pop('style', {'base_template': 'textarea.html'})
    return serializers.CharField(style=style, **kwargs)


class _RangeField(RangeField):

    def to_internal_value(self, data):
        if html.is_html_input(data):
            data = html.parse_html_dict(data)
        if not isinstance(data, dict):
            self.fail('not_a_dict', input_type=type(data).__name__)

        lower, upper = data.get('start_time'), data.get('end_time')
        data = {'lower': lower, 'upper': upper}
        return super().to_internal_value(data)

    def to_representation(self, value):
        """
        Range instances -> dicts of primitive datatypes.
        """
        if value.isempty:
            return {'empty': True}
        lower = self.child.to_representation(value.lower) if value.lower is not None else None
        upper = self.child.to_representation(value.upper) if value.upper is not None else None
        return {'start_time': lower,
                'end_time': upper
                }


class DateTimeRangeField(_RangeField):
    child = DateTimeField(allow_null=True)
    range_type = DateTimeTZRange
