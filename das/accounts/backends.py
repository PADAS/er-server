from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType


class AccountsModelBackend(ModelBackend):
    """
    Handle hierarchical groups and obj permissions.

    Inspired by Django-Guardian
    """

    def get_user_permissions(self, user_obj, obj=None):
        """
        Accounts model does not have permissions assigned to users.
        """
        return set()

    def get_group_permissions(self, user_obj, obj=None):
        """
        Returns a set of permission strings that this user has through his/her
        groups and their children.
        """
        if not hasattr(user_obj, '_group_perm_cache'):
            if user_obj.is_superuser:
                perms = Permission.objects.all()
            else:
                user_ps_ids = user_obj.get_all_permission_sets(only_ids=True)
                if obj and hasattr(obj, 'get_obj_permission_set_ids'):
                    obj_ps_ids = obj.get_obj_permission_set_ids(obj)
                    intersect_ids = user_ps_ids & obj_ps_ids

                    perms = Permission.objects.filter(permissionset__in=intersect_ids)
                else:
                    perms = Permission.objects.filter(permissionset__in=user_ps_ids)

            perms = perms.values_list('content_type__app_label', 'codename').order_by()
            user_obj._group_perm_cache = set(["%s.%s" % (ct, name) for ct, name in perms])
        return user_obj._group_perm_cache

    def get_all_permissions(self, user_obj, obj=None):
        """
        Returns a set of permission strings that the given ``user_obj`` has for ``obj``
        """
        if not user_obj.is_active or user_obj.is_anonymous():
            return set()
        return self.get_group_permissions(user_obj, obj)

    def has_perm(self, user_obj, perm, obj=None):
        """
        Returns ``True`` if given ``user_obj`` has ``perm`` for ``obj``. If no
        ``obj`` is given, ``False`` is returned.

        .. note::

           Remember, that if user is not *active*, all checks would return
           ``False``.

        Main difference between Django's ``ModelBackend`` is that we can pass
        ``obj`` instance here and ``perm`` doesn't have to contain
        ``app_label`` as it can be retrieved from given ``obj``.

        **Inactive user support**

        If user is authenticated but inactive at the same time, all checks
        always returns ``False``.
        """
        if '.' in perm:
            app_label, perm = perm.split('.')
            if app_label != obj._meta.app_label:
                raise ValueError("Passed perm has app label of '%s' and "
                                    "given obj has '%s'" % (app_label, obj._meta.app_label))

        perm = perm.split('.')[-1]
        if user_obj and not user_obj.is_active:
            return False
        elif user_obj and user_obj.is_superuser:
            return True
        return perm in self.get_all_permissions(user_obj, obj)

    def get_local_cache_key(self, obj):
        """
        Returns cache key for ``_obj_perms_cache`` dict.
        """
        ctype = ContentType.objects.get_for_model(obj)
        return (ctype.id, obj.pk)