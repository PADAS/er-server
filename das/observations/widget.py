from django import forms
from django.utils.translation import ugettext_lazy as _
from django.forms.widgets import MultiWidget


class LatLonWidget(MultiWidget):
    """
    A widget that is composed of multiple widgets.
    """

    def __init__(self, attrs=None):
        widgets = (forms.TextInput(), forms.TextInput)
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return [value.x, value.y]
        return [None, None]


class LatLonInput(forms.TextInput):

    def __init__(self, attrs=None):
        final_attrs = {'size': '25'}
        if attrs is not None:
            final_attrs.update(attrs)
        super().__init__(attrs=final_attrs)


class LatLon(LatLonWidget):
    """Widget with some css-specific styling"""

    template_name = 'admin/split_lat_lon.html'

    def __init__(self, attrs=None):
        widgets = [LatLonInput, LatLonInput]
        forms.MultiWidget.__init__(self, widgets, attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['lon_label'] = _('Longitude:')
        context['lat_label'] = _('Latitude:')
        return context

    class Media:
        css = {
            'all': ('css/split_lat_lon.css',),
        }


class CoordinateField(forms.MultiValueField):
    widget = LatLon

    def __init__(self, *args, **kwargs):
        fields = (forms.CharField(), forms.CharField())
        super().__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        if data_list:
            fmt = 'SRID={0};POINT({1} {2})'
            long, lat = data_list[0], data_list[1]
            return fmt.format('4326', long, lat)
        return None


# class ObservationForm(forms.ModelForm):
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.fields['Point_Coordinate'].initial = self.instance.location
#
#     Point_Coordinate = CoordinateField(required=False)
#
#     class Meta:
#         model = models.Observation
#         fields = "__all__"
#
#     def _correlate_field(self, data, fields):
#         # Forms a correlation between two fields: location and point_coordinate.
#         # Gets to update location point when not defined (Uses point_coordinate if present).
#         name_field = 'Point_Coordinate'
#         field = fields.get(name_field)
#         value = field.widget.value_from_datadict(self.data, self.files, self.add_prefix(name_field))
#         if data.get('location') == '' and value:
#             return field.clean(value)
#
#     def _clean_fields(self):
#         for name, field in self.fields.items():
#             # value_from_datadict() gets the data from the data dictionaries.
#             # Each widget type knows how to retrieve its own data, because some
#             # widgets split data over several HTML fields.
#             if field.disabled:
#                 value = self.get_initial_for_field(field, name)
#             else:
#                 value = field.widget.value_from_datadict(self.data, self.files, self.add_prefix(name))
#             try:
#                 if isinstance(field, forms.FileField):
#                     initial = self.get_initial_for_field(field, name)
#                     value = field.clean(value, initial)
#                 else:
#                     if name == 'location' and value == '':
#                         value = self._correlate_field(self.data, self.fields)
#                     else:
#                         value = field.clean(value)
#                 self.cleaned_data[name] = value
#                 if hasattr(self, 'clean_%s' % name):
#                     value = getattr(self, 'clean_%s' % name)()
#                     self.cleaned_data[name] = value
#             except ValidationError as e:
#                 self.add_error(name, e)
