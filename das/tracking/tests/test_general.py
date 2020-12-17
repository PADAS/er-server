import logging
from django.test import TestCase

from tracking.models.plugin_base import TrackingPlugin
from tracking.models import runnable_plugins

logger = logging.getLogger(__name__)

class GeneralTestsForTracking(TestCase):

    def setUp(self):
        pass

    def test_list_of_runnable_plugins(self):
        '''
        Ensure that all the classes included in runnable_plugins are of the right type.
        '''
        for rp in runnable_plugins:
            self.assertTrue(issubclass(rp, (TrackingPlugin)))