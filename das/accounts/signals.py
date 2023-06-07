from datetime import datetime

import pytz
from oauth2_provider.models import AccessToken

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=AccessToken, dispatch_uid="record_last_login")
def record_login(sender, instance, created, **kwargs):
    if created:
        instance.user.last_login = datetime.now(tz=pytz.utc)
        instance.user.save()
