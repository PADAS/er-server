
from business_rules import run_all

from core.utils import NonHttpRequest

from activity.models import AlertRule, NotificationMethod
from activity.businessrules import _generate_aggregate_event_variables_class, render_event, \
    EventActions


def get_alertrules_for_event(event):
    # Get Alert Rules that match the given event.
    pass


def evaluate_event_on_alertrules(alert_rule, event):

    # Constitute an EventVariables class
    event_variables, _ = _generate_aggregate_event_variables_class({event.event_type})

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
        },
    ]

    rendered_event = render_event(event, alert_rule.owner)

    action_list = []
    # Process the event against the single alert rule
    run_all(rule_list=rendered_rules,
            defined_variables=event_variables(rendered_event),
            defined_actions=EventActions(rendered_event, action_list),
            stop_on_first_trigger=False)

    return action_list


# This example alert rule illustrates the make up of what the business-rules library is expecting.
# example_alert_rules = [
#     {
#         "conditions": {
#             "all": [
#                 {
#                     "name": "priority",
#                     "operator": "shares_at_least_one_element_with",
#                     "value": ['1', '100', '200', ],
#                 },
#                 {
#                     "name": "state",
#                     "operator": "shares_at_least_one_element_with",
#                     "value": ["active", "new", ],
#                 },
#                 {
#                     'name': 'carcassrep_species',
#                     'operator': 'is_contained_by',
#                     'value': ['redriverhog', ],
#                 }
#             ]
#         },
#
#         "actions": [
#             {
#                 "name": "send_alert",
#                 "params": {
#                     "notification_methods": ["some method",],
#                 }
#             }
#         ]
#     },
# ]
