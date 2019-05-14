import json
import logging

from django.template.loader import render_to_string

from activity.alerting.businessrules import render_event
from activity.alerting.legacymailer import *
from activity.models import Event, NotificationMethod, AlertRule
from das_server import mailer
from reports.distribution import send_report

logger = logging.getLogger(__name__)


def send_event_alert(alert_rule_id=None, event_id=None, notification_method_id=None):
    '''
    Resolve the necessary objects for sending an alert.
    :param alert_rule_id:
    :param event_id:
    :param notification_method_id:
    :return:
    '''
    event, notification_method, alert_rule = None, None, None
    try:
        event = Event.objects.get(id=event_id)
        notification_method = NotificationMethod.objects.get(id=notification_method_id)
        alert_rule = AlertRule.objects.get(id=alert_rule_id)
    except Event.DoesNotExist:
        logger.exception(f'No Event found for id: {event_id}')
    except NotificationMethod.DoesNotExist:
        logger.exception(f'No NotificationMethod found for id: {notification_method_id}')
    except AlertRule.DoesNotExist:
        logger.exception(f'No AlertRule found for id: {alert_rule_id}')

    if any((x is None for x in [event, notification_method, alert_rule])):
        raise ValueError(f'Cannot continue with event={event}, '
                         f'alert_rule={alert_rule}, notification_method={notification_method}')

    # Get Revisions
    event_revision, details_revision = resolve_event_revisions(event)

    # Calculate updated fields
    updated_event_fields = get_revised_event_fields(event_revision)
    updated_event_details_fields = get_revised_event_details_fields(details_revision)

    if 'priority' in updated_event_fields:
        updated_event_fields['priority']['new'] = event.get_priority_display()
        updated_event_fields['priority']['old'] = Event(priority=updated_event_fields['priority']['old'])\
            .get_priority_display()

    report_context = render_event_alert_context(alert_rule, event, notification_method,
                                                event_revisions=updated_event_fields,
                                                event_details_revisions=updated_event_details_fields)

    revisions = []

    if event_revision:
        revisions.append(f'e;{event_revision.id}')
    if details_revision:
        revisions.append(f'd;{details_revision.id};{details_revision.object_id}')

    deep_event_data = extract_event_data(event, notification_method.owner, revisions)
    print(f'Legacy data: {json.dumps(deep_event_data, indent=2, default=str)}')
    print(f'Report context: {json.dumps(report_context, indent=2, default=str)}')

    print(f'Update Event Fields: {json.dumps(updated_event_fields, indent=2, default=str)}')
    print(f'Update Event Details Fields: {json.dumps(updated_event_details_fields, indent=2, default=str)}')
    email_body = render_to_string('eventalert.html', report_context)

    print(email_body)
    if notification_method.method == 'email':
        logger.debug(f"Sending email alert {event_id} to {notification_method.value}")
        send_report(
            subject=report_context['message_subject'],
            to_email=notification_method.value,
            html_content=email_body,
            text_content=f'EarthRanger Alert (attached as HTML).'
        )
        logger.info(f"Sent email alert {event_id} to {notification_method.value}")

    elif notification_method.method.lower() == 'sms':
        logger.debug(f"Sending sms alert {event_id} to {notification_method.value}")
        parameters = {
            'serial_number': event.serial_number,
            'color': 'gray',
            'title': event.title
        }
        msg = render_to_string('new_event_sms.txt', parameters).strip()
        mailer.send_sms(msg, notification_method.value)
        logger.info(f"Sent sms alert {event_id} to {notification_method.value}")

    else:
        logger.error(f"Unsupported NotifcationMethod ({notification_method.method})"
                     f" when processing event:{event_id} for notification: {notification_method.id}")


def get_revised_event_fields(event_revision):

    if not event_revision:
        return {}

    try:
        previous_version = event_revision.get_previous_by_revision_at(object_id=event_revision.object_id)
    except ObjectDoesNotExist:
        return {}
    else:
        current_data = event_revision.data
        previous_data = previous_version.data
        revision_changes = dict_changes(current_data, previous_data)
        return revision_changes


def get_revised_event_details_fields(event_details_revision):
    '''

    :param event_details_revision:
    :return:
    '''
    if not event_details_revision:
        return {}

    try:
        previous_version = event_details_revision.get_previous_by_revision_at(object_id=event_details_revision.object_id)
    except ObjectDoesNotExist:
        return {}
    else:
        print(f'Previous revision is: {previous_version}')

        current_data = event_details_revision.data['data'].get('event_details')
        previous_data = previous_version.data['data'].get('event_details')
        revision_changes = dict_changes(current_data, previous_data)
        return revision_changes

#
# def _comparator(this, that):
#     if type(this) != type(that):
#         return False
#
#     if isinstance(this, dict):
#         return not any((repr(this[k]) != repr(that[k])) for k in this.keys())
#     else:
#         return this != that

def dict_changes(current, previous, ignore_these=('sort_at', 'updated_at', 'created_at')):
    '''
    Given two dicts, determine which if any fields changed and report the change back in the form
    {
       'changed_key': {'old': <old-value>, 'new': <new-value' }
    }
    :param current:
    :param previous:
    :param ignore_these: a list of keys to ignore.
    :return:
    '''
    # delta = dict(set(current.items()) - set(previous.items()))
    # changes = dict((k, {'new': v, 'old': previous[k]}) for k, v in delta.items() if k not in ignore_these)

    changes = dict((k, {'new': v, 'old': previous.get(k)}) for k, v in current.items() if k not in ignore_these \
                   and v != previous.get(k))
    return changes


from activity.alerting.legacymailer import _get_title_from_schema

priority_label_colors = {'Red': '#c00',
                         'Amber': '#FFC300',
                         'Green': '#1D8348'
                         }

priority_label_color_default = '#566573'

def render_event_alert_context(alert_rule, event, notification_method,
                               event_revisions=None,
                               event_details_revisions=None):
    '''
    Render an alert context for the given parameters. Assume that the parameters are
    valid and that permissions have been respected.
    :param alert_rule: The alert rule that indicated the message.
    :param event:
    :param notification_method: The method for sending the alert.
    :return: A dict containing the alert context.
    '''
    eventdata = render_event(event, notification_method.owner)

    eventdata['title'] = eventdata['title'] or event.title

    logger.debug('Rendered event: %s', json.dumps(eventdata, indent=2, default=str))

    # Render display titles and values
    schema = utils.schema_utils.get_rendered_schema(event.event_type.schema)

    pretty_details = {}
    for k, internal_value in eventdata['event_details'].items():
        key_display = _get_title_from_schema(k, schema)
        rendered_value = internal_value.get('name') if isinstance(internal_value, dict) else internal_value
        pretty_details[k] = {'title': key_display,
                             'value': rendered_value}
        old_internal_value = event_details_revisions.get(k)
        if old_internal_value:
            old_internal_value = old_internal_value.get('old')
            rendered_old_value = old_internal_value.get('name') \
                if isinstance(old_internal_value, dict) else old_internal_value

            pretty_details[k]['old_value'] = rendered_old_value

    priority_color = priority_label_colors.get(event.priority_label, priority_label_color_default)

    report_context = {
        'message_subject': create_email_subject(event),
        'alert_rule': alert_rule.title,
        'event': {
            'time': {'title': 'Event Time', 'value': event.event_time},
            'priority': {'title': 'Priority', 'value': event.priority_label,
                         'style': f'color:{priority_color}'},
            'title': {'title': 'Title', 'value': eventdata['title']},
        },
        'raw_event_details': eventdata['event_details'],
        'pretty_details': pretty_details,
    }

    # extract_event_data(event)

    return report_context


def create_email_subject(event):
    priority = event.priority_label
    title = event.title or event.event_type.display

    return f"EarthRanger {priority} Alert: [{event.serial_number}] {title}"


