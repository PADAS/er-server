from datetime import datetime
import pytz

import logging

from django.apps import apps
from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.contrib.auth.management import _get_all_permissions
from django.contrib.auth.models import Permission
from django.contrib import auth
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import models

from observations.models import Observation, SubjectStatus, Subject, EMPTY_POINT, SubjectSource, SubjectStatus, SubjectGroup
from observations.utils import VIEW_END_WINDOWS, VIEW_SUBJECTGROUP_PERMS
from accounts.models import PermissionSet

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Observation)
def observation_post_save(sender, instance, created, **kwargs):

    # disable the handler during fixture loading
    if kwargs['raw']:
        return

    observation = Observation.objects.get(id=instance.id)
    SubjectStatus.objects.update_current_from_source(observation.source)


@receiver(post_save, sender=SubjectStatus)
def subject_status_post_save(sender, instance, created, **kwargs):

    if kwargs['raw']:
        return

    # Looking for name change.
    if instance.delay_hours == 0:
        latest_subject_name = instance.additional.get('subject_name', None)
        if latest_subject_name and latest_subject_name != instance.subject.name:
            logger.debug('Detected subject name change from %s to %s',
                         instance.subject.name, latest_subject_name)
            instance.subject.name = latest_subject_name
            instance.subject.save()


@receiver(post_save, sender=Subject)
def ensure_subject_status_exists(sender, **kwargs):

    if kwargs.get('created', False):
        subject = kwargs.get('instance')
        SubjectStatus.objects.ensure_for_subject(subject)


@receiver(post_save, sender=SubjectSource)
def maintain_subjectstatus(sender, instance, created, **kwargs):

    # This function is triggered when source is updated for subject.
    SubjectStatus.objects.maintain_subject_status(instance.subject_id)


def create_proxy_permissions(**kwargs):
    """
    Creates permissions for proxy models which are not created automatically
    by "django.contrib.auth.management.create_permissions"
    see issue[bug]: https://code.djangoproject.com/ticket/11154, however, it has been fixed
    in Django release 2.2
    What this method does is create new permissions for all proxy models,
    using their own content type instead of the content type of the concrete model.
    """
    for model in apps.get_models():
        opts = model._meta

        if not opts.proxy:
            continue
        # The content_type creation is needed for the tests
        proxy_content_type, __ = ContentType.objects.get_or_create(
            app_label=opts.app_label, model=opts.model_name)
        concrete_content_type = ContentType.objects.get_for_model(
            model, for_concrete_model=True)

        for code_tuple in _get_all_permissions(opts):
            codename = code_tuple[0]
            name = code_tuple[1]
            # Delete the automatically generated permission from Django
            Permission.objects.filter(
                codename=codename,
                content_type=concrete_content_type).delete()
            # Create the correct permission for the proxy model
            Permission.objects.get_or_create(codename=codename,
                                             content_type=proxy_content_type,
                                             defaults={
                                                 'name': name,
                                             })

post_migrate.connect(create_proxy_permissions)

def create_view_permissionset():
    user = auth.get_user_model()
    content_type = ContentType.objects.get_for_model(SubjectGroup)
    permission, _ = models.Permission.objects.get_or_create(
        codename='view_subjectgroup',
        content_type=content_type,
        defaults={'name': 'Permission to view a subject group'})
def create_view_permissionset(subject_name):
    permissions = {
        'view_subjectgroup': 'Permission to view a subject group',
        'change_subjectgroup': 'can change subjectgroup'
    }

    content_type = ContentType.objects.get_for_model(SubjectGroup)
    permission_set = PermissionSet.objects.create(name=f"View {subject_name} SubjectGroup")

    for codename, name in permissions.items():
        permission, _ = models.Permission.objects.get_or_create(
            codename=codename,
            content_type=content_type,
            defaults={'name': name})
        permission_set.permissions.add(permission)

@receiver(post_save, sender=SubjectGroup)
def auto_create_view_perm(sender, instance, created, **kwargs):
    if created:
        subject_name = instance.name
        create_view_permissionset(subject_name)
        permission_set = PermissionSet.objects.get(name=f'View {subject_name} SubjectGroup')

        queryset = SubjectGroup.objects.get(id=instance.id)
        queryset.permission_sets.add(permission_set)
