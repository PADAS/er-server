from django.test import TestCase
from observations.models import Subject, Source, SubjectSource, SubjectGroup, Observation, SubjectTrackSegmentFilter, \
    DEFAULT_ASSIGNED_RANGE
from analyzers.models import SubjectAnalyzerResult, LowSpeedPercentileAnalyzerConfig, LowSpeedWilcoxAnalyzerConfig
import logging
from analyzers import finder

logger = logging.getLogger(__name__)


class TestLowSpeedAnalyzer(TestCase):

    def test_analyzer_finder(self):

        # Create models to test whether we accurately find the analyzer configs
        # for a Subject.
        sub = Subject.objects.create(
            name='Dinky', subject_subtype_id='elephant')

        source = Source.objects.create(manufacturer_id='xyz-000001')

        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='xyz_analyzer_group', )
        sg.subjects.add(sub)
        sg.save()

        a1 = LowSpeedWilcoxAnalyzerConfig.objects.create(subject_group=sg)

        # Find analyzers for this subject.
        alist = list(finder.get_subject_analyzers(sub))
        a = alist[0] if alist else None
        aid = a.config.id if a else ''
        self.assertEqual(a1.id, aid)
