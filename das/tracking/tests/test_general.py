import logging

from django.test import TestCase

from tracking.models import runnable_plugins
from tracking.models.plugin_base import TrackingPlugin

logger = logging.getLogger(__name__)


class GeneralTestsForTracking(TestCase):

    def setUp(self):
        pass

    def test_list_of_runnable_plugins(self):
        '''
        Ensure that all the classes included in runnable_plugins are of the right type.
        '''
        for rp in runnable_plugins:
            self.assertTrue(issubclass(rp, (TrackingPlugin)),
                            msg=f'Please remove {rp.__module__}.{rp.__name__} from the list of runnable_plugins.')
