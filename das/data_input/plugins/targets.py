__author__ = 'chris'

from observations.models import Observation, Source
from django.contrib.gis.geos import Point


class PluginTarget(object):
    pass


class DasPluginTarget(PluginTarget):
    def __init__(self, config=None):
        self.__config = config

    def __call__(self, *args, **kwargs):

        def _(obj):
            cnt = 0
            try:
                while True:
                    item = (yield)
                    print(item)
                    cnt += 1

            except GeneratorExit:
                print("You sent %d messages" % (cnt,))

    def insert(self, observation):
        '''
        Expect observation to be a dict mapping to observation model
        :param observation:
        :return:
        '''
        source = Source.objects.get(model_name=observation.source_model_name, manufacturer_id=observation.collar_id)

        loc = Point(float(observation.pop('lat')), float(observation.pop('lon')))
        ts = observation.pop('ts')

        obs = Observation(source=source, location=loc, recorded_at=ts, additional=observation)
        obs.save()
