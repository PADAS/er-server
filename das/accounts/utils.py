from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q


def patrol_mgmt_permissions(modelnames=None):
    modelnames = modelnames or ('patrol', 'patroltype', 'patrolsegment', 'patrolnote',
                                'patrolfile', 'patrolsegmentmembership')

    content_types = [ContentType.objects.get(app_label='activity', model=modelname) for modelname in modelnames]
    return Permission.objects.filter(content_type__in=content_types)


def allowed_permissions(instance, model_name, app_label='activity'):
    perms_sets_ids = instance.get_all_permission_sets(only_ids=True)
    perms = Permission.objects.filter(Q(permission_sets__in=perms_sets_ids) &
                                      Q(content_type=ContentType.objects.get(app_label=app_label, model=model_name)))
    perms = perms.distinct()
    return list(perms.values_list('codename', flat=True))
