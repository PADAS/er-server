from django.forms import DateTimeField
from django.test import TestCase
from django.utils import lorem_ipsum, timezone

from activity.alerting.message import coerce_state_value
from activity.models import Event

ET_OTHER = 'other'

class TestAlerts(TestCase):
    def setUp(self) -> None:
        self.states = [{'name': 'New', 'value': 'new'},
                  {'name': 'Active', 'value': 'active'},
                  {'name': 'Resolved', 'value': 'resolved'}]

        self.event_data = dict(
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_SYSTEM,
            event_type=ET_OTHER,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude='40.1353', latitude='-1.891517'),
        )

    def test_alert_coerces_to_the_right_state_val(self):
        for state in self.states:
            self.assertEqual(state.get('name'), coerce_state_value(val=state.get('value')))

    def test_alert_coerces_event_to_right_state(self):
        self.fail()




