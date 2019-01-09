import random
import datetime

from django.test import TestCase
import django.contrib.auth
from pytz import UTC

from observations.serializers import ObservationSerializer
from observations.views import SubjectStatusView
from rt_api.tasks import get_subjectstatus_view

User = django.contrib.auth.get_user_model()


class RTTasksTestCase(TestCase):
    fixtures = [
        'test/sourceprovider.yaml',
        'test/rt_api_source.json',
        'test/rt_api_subject.json',
        'test/rt_api_subject_source.json',
        'test/rt_api_observation.json',
        'initial_admin.yaml'
    ]

    def test_contain_last_voice(self):
        user = User.objects.get(username='admin')
        subject_id = 'a51d6901-4ece-484f-b0a6-baf1e44d2108'
        source_id = '43d22e4d-debf-402d-b49b-efdc67dddb93'

        # Generate some random data for the observation.
        observation_time = UTC.localize(datetime.datetime.now())
        fixed_latitude = float(random.randint(3000, 3000)) / 100
        fixed_longitude = float(random.randint(2800, 4000)) / 100

        fixed_location = dict(longitude=fixed_longitude,
                              latitude=fixed_latitude)

        observation = {
            'location': fixed_location,
            'recorded_at': observation_time,
            'source': source_id,
            'additional': {
                "last_voice_call_start_at": "2018-06-22T04:57:57.058000+00:00",
                "received_time": "2018-05-09T04:55:16.000000Z",
                "state": "offline"}
        }

        serializer = ObservationSerializer(data=observation)

        self.assertTrue(serializer.is_valid(),
                        msg='Observation is not valid.')

        observation_instance = None
        if serializer.is_valid():
            observation_instance = serializer.save()

        result = get_subjectstatus_view(
            SubjectStatusView.as_view(), user, subject_id)

        self.assertIn('last_voice_call_start_at', result['properties'])
        print(result)
