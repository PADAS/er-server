# from django import forms
# from django.utils.translation import ugettext_lazy as _
# from django.forms.widgets import MultiWidget


# class LatLonWidget(MultiWidget):
#     """
#     A widget that is composed of multiple widgets.
#     """

#     def __init__(self, attrs=None):
#         widgets = (forms.TextInput(), forms.TextInput)
#         super().__init__(widgets, attrs)

#     def decompress(self, value):
#         if value:
#             return [value.x, value.y]
#         return [None, None]


# class LatLonInput(forms.TextInput):

#     def __init__(self, attrs=None):
#         final_attrs = {'size': '25'}
#         if attrs is not None:
#             final_attrs.update(attrs)
#         super().__init__(attrs=final_attrs)


# class LatLon(LatLonWidget):
#     """Widget with some css-specific styling"""

#     template_name = 'admin/split_lat_lon.html'

#     def __init__(self, attrs=None):
#         widgets = [LatLonInput, LatLonInput]
#         forms.MultiWidget.__init__(self, widgets, attrs)

#     def get_context(self, name, value, attrs):
#         context = super().get_context(name, value, attrs)
#         context['lon_label'] = _('Longitude:')
#         context['lat_label'] = _('Latitude:')
#         return context

#     class Media:
#         css = {
#             'all': ('css/split_lat_lon.css',),
#         }


# class CoordinateField(forms.MultiValueField):
#     widget = LatLon

#     def __init__(self, *args, **kwargs):
#         fields = (forms.CharField(), forms.CharField())
#         super().__init__(fields, *args, **kwargs)

#     @staticmethod
#     def _validate(data_list):
#         empty_string = ''
#         for i in data_list:
#             if i != empty_string:
#                 try:
#                     float(i)
#                 except ValueError:
#                     raise forms.ValidationError("Invalid Coordinate.")
#         return data_list

#     def compress(self, data_list):
#         data_list = self._validate(data_list)
#         if data_list:
#             fmt = 'SRID={0};POINT({1} {2})'
#             long, lat = data_list[0], data_list[1]
#             return fmt.format('4326', long, lat)
#         return None


