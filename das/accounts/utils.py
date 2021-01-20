from collections import defaultdict
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType


def patrol_mgmt_permissions(modelnames=None):
    modelnames = modelnames or ('patrol', 'patroltype', 'patrolsegment', 'patrolnote',
                                'patrolfile', 'patrolsegmentmembership')

    content_types = [ContentType.objects.get(app_label='activity', model=modelname) for modelname in modelnames]
    return Permission.objects.filter(content_type__in=content_types)


def allowed_permissions(user_instance, model_names, app_label):
    permissions = Permission.objects.filter(permission_sets__user=user_instance,
                                            content_type__app_label=app_label,
                                            content_type__model__in=model_names).distinct()

    container = defaultdict(list)
    permissions = permissions.values_list('content_type__model', 'codename')
    for modelname, action in permissions:
        container[modelname].append(action.split('_')[0])
    return container
