import logging

from django.views.generic import View
from django.http import Http404, JsonResponse

from observations.models import Subject, Observation, SubjectSource
from das_server import utils

logger = logging.getLogger(__name__)


class AnimalsView(View):
    fields = ('id', 'name')
    def get(self, request):
        animals = Subject.objects.all()
        result = []
        for animal in animals:
            result.append({k: getattr(animal, k) for k in self.fields})
        return JsonResponse(result, encoder=utils.ExtendedJSONEncoder, safe=False)


class AnimalTrackView(View):
    def get(self, request, id):
        try:
            subject = Subject.objects.get(id=id)
        except Subject.DoesNotExist:
            return Http404

        color = subject.additional.get('rgb', None)
        if color:
            color = "#" + "".join(color.split(','))

        sds = SubjectSource.objects.filter(subject_id=id)
        if not sds:
            raise Http404
        observations = Observation.objects.get_source_range_observations(sds)
        coordinates = []
        times = []
        for ob in observations:
            coordinates.append(ob.location.coords)
            times.append(ob.recorded_at)

        feature = {
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "type": "Feature",
            "properties": {
                "name": subject.name,
            },

        }
        if color:
            feature['style'] = {
                "color": color,
                "iconUrl": "http://107.21.94.89/Images/AnimalIcons/Elephant_Male.png",
                "opacity": 1
            }
        #see https://github.com/mapbox/geojson-coordinate-properties
        feature['properties']['coordinateProperties'] = {'times': times}

        result = utils.empty_geojson_featurecollection()
        result['features'].append(feature)
        return JsonResponse(result, encoder=utils.ExtendedJSONEncoder)


