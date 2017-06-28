from django import forms
from mapping.models import Map
from django.contrib.gis.geos import Point


class MapCenterForm(forms.ModelForm):

    latitude = forms.FloatField(
        min_value=-90,
        max_value=90,
        required=True,
    )
    longitude = forms.FloatField(
        min_value=-180,
        max_value=180,
        required=True,
    )

    class Meta(object):
        model = Map
        exclude = []
        widgets = {'center': forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.coordinates = self.initial.get('center', None)
        if isinstance(self.coordinates, Point):
            self.initial['latitude'], self.initial['longitude'] = self.coordinates.tuple

    def clean(self):
        data = super().clean()
        map_control_center = data.get('center')
        # If they've manipulated the map, use the coordinates from that.
        # However, if they haven't touched the map, AND have entered new
        # coordinates manually, then we want to use the new coordinates
        if map_control_center.tuple == self.coordinates.tuple:
            latitude = data.get('latitude', None)
            longitude = data.get('longitude', None)
            if latitude != self.initial['latitude'] or longitude != self.initial['longitude']:
                data['center'] = Point(latitude, longitude)
        return data
