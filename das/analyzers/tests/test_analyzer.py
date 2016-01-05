from django.test import TestCase
from analyzers.models.analyzer import Analyzer


class TestAnalyzer(TestCase):

    fixtures = ['observations_source.json']

    def setUp(self):
        pass

    def test_analyzer(self):
        """
        Test generic analyzer
        """

        self.assertRaises(TypeError, Analyzer())
