from datetime import datetime, timezone

from oauth2_provider.models import get_access_token_model

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from accounts.models import User
from accounts.utils import add_tenant_to_permission_codename, parse_permission_codename
from utils.tenant import get_tenant_settings
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException

AccessToken = get_access_token_model()

TENANT_CODENAME_OVERRIDES = [dict(app_label="activity", model="event")]


@receiver(post_save, sender=AccessToken, dispatch_uid="record_last_login")
def record_login(sender, instance, created, **kwargs):
    if created:
        instance.user.last_login = datetime.now(tz=timezone.utc)
        instance.user.save()


@receiver(post_save, sender=User, dispatch_uid="user_linked_subject_name")
def update_linked_subject_name(sender, instance, created, **kwargs):
    if hasattr(instance, "linked_subject"):
        full_name = instance.get_full_name()
        instance.linked_subject.name = full_name if full_name else instance.username
        instance.linked_subject.save(update_fields=["name"])


@receiver(pre_save, sender=Permission)
def permission_codename_pre_save(sender, instance, raw, using, update_fields, **kwargs):
    for override in TENANT_CODENAME_OVERRIDES:
        try:
            content_type = ContentType.objects.get(app_label=override["app_label"], model=override["model"])
            if instance.content_type == content_type:
                try:
                    tenant_id = get_tenant_settings().id
                except TenantNotFoundInLocalThreadException:
                    return
                pre_save_tenant_id, pre_save_codename = parse_permission_codename(instance.codename)
                if not pre_save_tenant_id:
                    instance.codename = add_tenant_to_permission_codename(
                        tenant_id=tenant_id, codename=instance.codename
                    )
                break
        except ContentType.DoesNotExist:
            pass
