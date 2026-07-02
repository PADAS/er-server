import logging
from datetime import datetime, timezone

from oauth2_provider.models import get_access_token_model

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from accounts.models import PermissionSet, PermissionSetPermission, User
from accounts.tile_cache import bump_user_tile_version
from accounts.utils import add_tenant_to_permission_codename, parse_permission_codename
from utils.tenant import get_tenant_settings
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException

logger = logging.getLogger(__name__)

AccessToken = get_access_token_model()

TENANT_CODENAME_OVERRIDES = [dict(app_label="activity", model="event")]


def _bump_user_tiles(user: User) -> None:
    """Best-effort: invalidate one user's cached vector tiles.

    Used when the user's identity/permissions change (token delete, permission-set
    membership, permission-set contents). Failures are swallowed because the short
    tile TTL is the backstop.
    """
    tenant_id = getattr(user, "das_tenant_id", None)
    user_id = getattr(user, "id", None)
    if tenant_id is None or user_id is None:
        return
    try:
        bump_user_tile_version(str(tenant_id), str(user_id))
    except Exception:  # pragma: no cover - defensive; TTL is the backstop
        logger.warning("Failed to bump user tile version for user %s", user_id, exc_info=True)


@receiver(post_delete, sender=AccessToken, dispatch_uid="bust_user_tiles_on_token_delete")
def bust_user_tiles_on_token_delete(sender, instance, **kwargs):
    """Bust a user's cached tiles when one of their access tokens is deleted.

    NOTE: queryset/bulk token revocations bypass ``post_delete``; the short tile
    TTL (a few minutes) is the backstop for those.
    """
    user = getattr(instance, "user", None)
    if user is not None:
        _bump_user_tiles(user)


@receiver(m2m_changed, sender=User.permission_sets.through, dispatch_uid="bust_user_tiles_on_membership_change")
def bust_user_tiles_on_membership_change(sender, instance, action, reverse, model, pk_set, **kwargs):
    """Bust cached tiles for users whose permission-set membership changes.

    Handles both directions of the M2M:
    - ``user.permission_sets`` add/remove/clear
    - ``permission_set.user_set`` add/remove/clear

    ``add`` / ``remove`` are handled in their ``post_*`` phase (``pk_set`` is
    populated). ``clear`` is handled in the ``pre_clear`` phase instead: Django
    delivers ``pk_set=None`` on ``post_clear`` in *both* directions, so the
    affected members must be captured before the through rows are deleted. In the
    reverse direction ``post_add``/``post_remove`` carry user ids; in the forward
    direction the changed member is ``instance`` itself.
    """
    if action in ("post_add", "post_remove"):
        if not reverse:
            # ``instance`` is a User; the changed permission sets do not affect
            # which user's tiles to bust — it is always this user.
            _bump_user_tiles(instance)
        else:
            # ``instance`` is a PermissionSet; ``pk_set`` holds the affected user ids.
            if pk_set:
                for user in User.objects.filter(pk__in=pk_set):
                    _bump_user_tiles(user)
    elif action == "pre_clear":
        # ``post_clear`` carries pk_set=None in both directions, so capture the
        # about-to-be-removed members now, before the relation rows are deleted.
        if not reverse:
            # ``instance`` is a User losing all its permission sets.
            _bump_user_tiles(instance)
        else:
            # ``instance`` is a PermissionSet losing all its members. Query members
            # via the forward relation (type-checkable) rather than the dynamically
            # created ``user_set`` reverse accessor.
            for user in User.objects.filter(permission_sets=instance):
                _bump_user_tiles(user)


def _bump_permission_set_members(permission_set: PermissionSet | None) -> None:
    """Bust cached tiles for all direct members of a permission set.

    Best effort: group-mediated permission sets and deep (ancestor) hierarchy edits
    are intentionally NOT chased per-user — the short tile TTL is the backstop for
    those less-common paths.
    """
    if permission_set is None:
        return
    # Use the forward relation so the type checker can resolve it (the reverse
    # ``user_set`` accessor is created dynamically and is not statically visible).
    for user in User.objects.filter(permission_sets=permission_set):
        _bump_user_tiles(user)


@receiver(post_save, sender=PermissionSetPermission, dispatch_uid="bust_user_tiles_on_psp_save")
@receiver(post_delete, sender=PermissionSetPermission, dispatch_uid="bust_user_tiles_on_psp_delete")
def bust_user_tiles_on_permission_set_permission_write(sender, instance, **kwargs):
    """Direct ``PermissionSetPermission`` writes (admin / ``.objects.create``)."""
    _bump_permission_set_members(getattr(instance, "permissionset", None))


@receiver(
    m2m_changed,
    sender=PermissionSet.permissions.through,
    dispatch_uid="bust_user_tiles_on_permission_set_contents_change",
)
def bust_user_tiles_on_permission_set_contents_change(sender, instance, action, reverse, model, pk_set, **kwargs):
    """Permission-set contents change via the ``permissions`` M2M (``add``/``remove``/``set``).

    The ``.add()`` path uses bulk_create on the through model, which does not fire
    ``PermissionSetPermission.post_save``; this handler covers that common path.
    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if not reverse:
        # ``instance`` is a PermissionSet.
        _bump_permission_set_members(instance)
    else:
        # ``instance`` is a Permission; pk_set holds permission-set ids.
        if pk_set:
            for permission_set in PermissionSet.objects.filter(pk__in=pk_set):
                _bump_permission_set_members(permission_set)


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
