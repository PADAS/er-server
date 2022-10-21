import activity.models


def get_update_type(revision, previous_revisions=[]):
    field_mapping = (('location', 'update_location'), ('message', 'update_message'),
                     ('event_time', 'update_datetime'), ('reported_by_id',
                                                         'update_reported_by'),
                     ('state', 'update_event_state'), ('priority',
                                                       'update_event_priority'),
                     ('event_type', 'update_event_type'))
    model_name = revision._meta.model_name
    action = revision.action
    data = revision.data
    if action == 'added':
        return 'add_{0}'.format(model_name.replace('revision', ''))
    elif action == 'updated':
        event_state = data.get('state', None)
        if event_state:
            if event_state == activity.models.Event.SC_RESOLVED:
                return activity.models.Event.SC_RESOLVED
            if event_state == activity.models.Event.SC_NEW:
                return 'mark_as_new'
            for row in reversed(previous_revisions):
                prev_state = row.data.get('state', None)
                if prev_state:
                    if prev_state == activity.models.Event.SC_RESOLVED:
                        return 'unresolved'
                    if (prev_state == activity.models.Event.SC_NEW
                            and event_state == activity.models.Event.SC_ACTIVE):
                        return 'read'
                    break
        for k, v in field_mapping:
            if k in data:
                return v
        return 'update_event'
    return 'other'


def get_user_display(user):
    if not user:
        return ''
    try:
        if user.get_full_name():
            return user.get_full_name()
    except NotImplementedError:
        pass
    return user.get_username()
