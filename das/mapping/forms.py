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
        self.starting_center = self.initial.get('center', None)
        if not isinstance(self.starting_center, Point):
            self.data['center'] = Point(0, 0)
            self.starting_center = self.data['center']

        if 'longitude' not in self.initial:
            self.initial['longitude'], self.initial['latitude'] = self.starting_center.tuple

    def clean(self):
        data = super().clean()
        map_control_center = data.get('center', None)
        latitude = data.get('latitude', None)
        longitude = data.get('longitude', None)
        if latitude and longitude:
            manual_center = Point(float(longitude), float(latitude))
        else:
            manual_center = None

        # If map control center exists and it's changed from the starting center
        # Use the data specified in the map control
        if map_control_center and not self.samepoint(map_control_center, self.starting_center):
            data['center'] = map_control_center
        # If the map control has not been changed, see if the manual latlon has
        # been changed, and use those as the new values
        elif manual_center and not self.samepoint(manual_center, self.starting_center):
            data['center'] = manual_center
        else:
            pass

        return data

    def samepoint(self, point_a, point_b):
        import math
        return math.isclose(point_a.x, point_b.x, rel_tol=1e-10) and math.isclose(point_a.y, point_b.y, rel_tol=1e-10)
