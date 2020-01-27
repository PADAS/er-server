# COORDINATES FOR POINT.
# from django.contrib.css.widgets import  AdminDateWidget, AdminTimeWidget
import pickle
from django import forms
from observations import models
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
            return pickle.loads(value)
        return ['1', '1']



class LatLonW(forms.TextInput):

    def __init__(self, attrs=None):
        final_attrs = {'size': '20', 'class': 'tx'}
        if attrs is not None:
            final_attrs.update(attrs)
        super().__init__(attrs=final_attrs)


class LatLon(LatLonWidget):
    """Widget with some css-specific styling"""
    # template_name = ""
    template_name = 'admin/split_lat_lon.html'

    def __init__(self, attrs=None):
        widgets = [LatLonW, LatLonW]
        forms.MultiWidget.__init__(self, widgets, attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['lat_label'] = _('Latitude:')
        context['lon_label'] = _('Longitude:')
        return context

    class Media:
        css = {
            'all': ('css/split_lat_lon.css',),
        }

class OForm(forms.ModelForm):
    Coordinate = forms.CharField(widget=LatLon)

    class Meta:
        model = models.Observation
        fields = "__all__"
