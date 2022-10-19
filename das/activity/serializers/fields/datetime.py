from dateutil.parser import parse as parse_date
from drf_extra_fields.fields import DateTimeRangeField as DRFDateTimeRangeField

from rest_framework.exceptions import ValidationError
from rest_framework.utils import html


class DateTimeRangeField(DRFDateTimeRangeField):
    # FUTURE: Remove this class and try to stick to lower and upper keys instead of start_time and end_time
    default_child_attrs = {"allow_null": True}

    def to_internal_value(self, data):
        if html.is_html_input(data):
            data = html.parse_html_dict(data)

        if isinstance(data, dict):
            lower, upper = data.get("start_time"), data.get("end_time")
            self.validate_time_range(lower, upper)
            data = {"lower": lower, "upper": upper}

        return super().to_internal_value(data)

    def validate_time_range(self, lower, upper):
        if lower and upper and parse_date(lower) > parse_date(upper):
            raise ValidationError("start_time must be an earlier date than the end_time")

    def to_representation(self, value):
        lower = self.child.to_representation(value.lower) if value.lower is not None else None
        upper = self.child.to_representation(value.upper) if value.upper is not None else None
        return {"start_time": lower, "end_time": upper}
