from datetime import datetime

import pytz
from oauth2_provider.models import get_access_token_model

from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import User

AccessToken = get_access_token_model()


@receiver(post_save, sender=AccessToken, dispatch_uid="record_last_login")
def record_login(sender, instance, created, **kwargs):
    if created:
        instance.user.last_login = datetime.now(tz=pytz.utc)
        instance.user.save()


@receiver(post_save, sender=User, dispatch_uid="user_linked_subject_name")
def update_linked_subject_name(sender, instance, created, **kwargs):
    if hasattr(instance, "linked_subject"):
        full_name = instance.get_full_name()
        instance.linked_subject.name = full_name if full_name else instance.username
        instance.linked_subject.save(update_fields=["name"])
