import pytz
from oauth2_provider.models import AccessToken
from django.dispatch import receiver
from django.db.models.signals import post_save
from datetime import datetime


@receiver(post_save, sender=AccessToken, dispatch_uid="record_last_login")
def record_login(sender, instance, created, **kwargs):
    if created:
        instance.user.last_login = datetime.now(tz=pytz.utc)
        instance.user.save()