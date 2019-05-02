import logging

from django.utils import timezone

from core.utils import OneWeekSchedule
from business_rules import run_all
from accounts.models import User

from activity.models import AlertRule
from activity.businessrules import _generate_aggregate_event_variables_class, render_event, \
    EventActions

logger = logging.getLogger(__name__)


def evaluate_event(event):

    alert_rules = AlertRule.objects.filter(event_types=event.event_type)
    return evaluate_event_on_alertrules(alert_rules, event)


def evaluate_event_on_alertrules(alert_rules, event):

    # Constitute an EventVariables class
    event_variables, _ = _generate_aggregate_event_variables_class({event.event_type})

    def filter_on_schedule(alert_rule):
        return timezone.localtime() in OneWeekSchedule(alert_rule.schedule.get('periods'))

    alert_rules = filter(filter_on_schedule, alert_rules)
    rendered_rules = [
        {
            'conditions': alert_rule.conditions,
            'actions': [
                {
                    "name": "send_alert",
                    "params": {
                        "notification_methods": [n.id for n in alert_rule.notification_methods.all()],
                    }
                }
            ]
        }
        for alert_rule in alert_rules
    ]

    # Here I render the Event as a superuser, to discount any restrictions on the various users
    # within the list of AlertRules. I will leave it up to the logic that sends alerts to determine
    # whether an individual user has read access.
    # TODO: Reconsider this since the alternative is to evaluate the Event+Rule once for each user.
    rendered_event = render_event(event, User(is_superuser=True))

    action_list = []
    # Process the event against the single alert rule
    run_all(rule_list=rendered_rules,
            defined_variables=event_variables(rendered_event),
            defined_actions=EventActions(rendered_event, action_list),
            stop_on_first_trigger=False)

    return action_list

