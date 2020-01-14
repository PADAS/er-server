from django.test import TestCase

from activity.alerting.message import coerce_state_value


class TestAlerts(TestCase):
    def test_alert_coarces_to_the_right_state(self):
        states = [{'name': 'New', 'value': 'new'}, {'name': 'Active', 'value': 'active'}, {'name': 'Resolved', 'value': 'resolved'}]

        for state in states:
            self.assertEqual(state.get('name'), coerce_state_value(state.get('value')))
