from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType


def patrol_mgmt_permissions():
    content_types = [ContentType.objects.get(app_label='activity', model=modelname)
                     for modelname in ('patrol', 'patroltype', 'patrolsegment', 'patrolnote',
                                       'patrolfile', 'patrolsegmentmembership')]
    return Permission.objects.filter(content_type__in=content_types)