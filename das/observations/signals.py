import logging

from django.apps import apps
from django.contrib.auth import models
from django.contrib.auth.management import _get_all_permissions
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import jsonb
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import (post_delete, post_migrate, post_save,
                                      pre_delete)
from django.dispatch import receiver

from accounts.models import PermissionSet
from das_server import pubsub
from observations.models import (Announcement, LatestObservationSource,
                                 Message, Observation, SourceProvider, Subject,
                                 SubjectGroup, SubjectSource, SubjectStatus)
from observations.servicesutils import SOURCE_PROVIDER_2WAY_MSG_KEY
from observations.utils import is_observation_stationary_subject

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Observation)
def observation_post_save(sender, instance, created, **kwargs):
    # disable the handler during fixture loading
    if kwargs["raw"]:
        return

    SubjectStatus.objects.update_current_from_source(
        instance.source, include_empty_location=is_observation_stationary_subject(
            instance)
    )


@receiver(post_delete, sender=Observation)
def observation_post_delete(sender, instance, **kwargs):
    SubjectStatus.objects.update_current_from_deleted_observation(instance)
    ensure_keep_latest_observation_source(instance)


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


def create_view_permissionset(permission_name):

    permission_set, created = PermissionSet.objects.get_or_create(
        name=permission_name)

    for codename in ['view_real_time', 'view_subject', 'subscribe_alerts', 'view_subjectgroup']:
        perms = models.Permission.objects.filter(codename=codename)
        for perm in perms:
            permission_set.permissions.add(perm)
    return permission_set


@receiver(post_save, sender=SubjectGroup)
def auto_create_view_perm(sender, instance, created, **kwargs):
    if created:
        permission_name = instance.auto_permissionset_name
        perm_set = create_view_permissionset(permission_name)
        permission_set = PermissionSet.objects.get(id=perm_set.id)

        # Add PermissionSet after commit
        transaction.on_commit(
            lambda: instance.permission_sets.add(permission_set))


@receiver(pre_delete, sender=SubjectGroup)
def delete_auto_created_view_permission_set(sender, instance, **kwargs):
    for permission_set in instance.permission_sets.all():
        search_list = {'View', 'Subject',  'Group'}
        if len(permission_set.subjectgroup_set.all()) == 1 and search_list.issubset(set(permission_set.name.split())):
            permission_set.delete()


@receiver(post_save, sender=SourceProvider)
def source_provider_post_save(sender, **kwargs):
    source_provider = SourceProvider.objects.annotate(two_way_message=jsonb.KeyTransform(
        'two_way_messaging', 'additional')
    ).exclude(Q(two_way_message__isnull=True) |
              Q(two_way_message=False)).exists()
    cache.set(SOURCE_PROVIDER_2WAY_MSG_KEY, source_provider, None)


@receiver(post_save, sender=Message)
def message_post_save(sender, instance, created, **kwargs):
    logger.info("saved message {}, created={}".format(
        instance.pk, str(created)))
    message_action = 'das.message.new' if created else 'das.message.update'
    transaction.on_commit(lambda: pubsub.publish(
        {'message_id': str(instance.pk)}, message_action))


@receiver(post_delete, sender=Message)
def message_post_delete(sender, instance, **kwargs):
    logger.info("delete message {}".format(instance.pk))
    transaction.on_commit(lambda: pubsub.publish(
        {'message_id': str(instance.pk)}, 'das.message.delete'))


@receiver(post_save, sender=Announcement)
def news_post_save(sender, instance, created, **kwargs):
    if created:
        logger.info("saved announcement {}, created={}".format(
            instance.pk, str(created)))
        action = 'das.announcement.new'
        transaction.on_commit(lambda: pubsub.publish(
            {'announcement_id': str(instance.pk)}, action))


def ensure_keep_latest_observation_source(observation):
    if (
            not LatestObservationSource.objects.filter(
                source=observation.source).exists()
            and observation.source.observation_set.count()
    ):
        latest_observation = observation.source.observation_set.order_by(
            "-recorded_at")[0]
        LatestObservationSource.objects.get_or_create(
            source=observation.source, observation=latest_observation, recorded_at=latest_observation.recorded_at
        )
