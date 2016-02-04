from __future__ import unicode_literals

import uuid
from django.contrib import auth
from django.contrib.gis.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, Permission
from django.utils.translation import ugettext_lazy as _
from django.core.mail import send_mail
from django.core.exceptions import PermissionDenied
from django.core import validators
from django.utils import six, timezone
from mptt.models import MPTTModel, TreeForeignKey, TreeManyToManyField, TreeManager


phone_regex = validators.RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")


class PermissionSetManager(models.Manager):
    """
    The manager for the accounts PermissionSet model.
    """
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class PermissionSet(MPTTModel):
    """
    PermissionSets are a generic way of categorizing users to apply permissions, or
    some other label, to those users. A user can belong to any number of
    groups.

    A user in a group automatically has all the permissions granted to that
    group. For example, if the group Site editors has the permission
    can_edit_home_page, any user in that group will have that permission.

    Beyond permissions, PermissionSets are a convenient way to categorize users to
    apply some label, or extended functionality, to them. For example, you
    could create a group 'Special users', and you could write code that would
    do special things to those users -- such as giving them access to a
    members-only portion of your site, or sending them members-only email
    messages.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=80, unique=True)
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
    )
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children',
        verbose_name=_('parent'), db_index=True,
        help_text=_('The permission set\'s parent set. None, if it is a root node.'))

    tree = TreeManager()
    objects = PermissionSetManager()

    class Meta:
        verbose_name = _('permission set')
        verbose_name_plural = _('permission sets')

    class MPTTMeta:
        order_insertion_by=['name']

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)

    def get_ancestor_ids(self):
        return [a.id for a in self.get_ancestors()]


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, password, **extra_fields):
        """
        Creates and saves a User with the given username, email and password.
        """
        if not username:
            raise ValueError('The given username must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)


def _user_has_module_perms(user, app_label):
    """
    A backend can raise `PermissionDenied` to short-circuit permission checking.
    """
    for backend in auth.get_backends():
        if not hasattr(backend, 'has_module_perms'):
            continue
        try:
            if backend.has_module_perms(user, app_label):
                return True
        except PermissionDenied:
            return False
    return False


class PermissionsMixin(models.Model):
    """
    A mixin class that adds the fields and methods necessary to support
    DAS's PermissionSet and Permission model using the AccountsModelBackend.
    """
    is_superuser = models.BooleanField(
        _('superuser status'),
        default=False,
        help_text=_(
            'Designates that this user has all permissions without '
            'explicitly assigning them.'
        ),
    )
    permission_sets = TreeManyToManyField(
        PermissionSet,
        blank=True,
        help_text=_(
            'The permission sets this user belongs to. A user will get all permissions '
            'granted to each of their permission sets.'
        ),
    )

    class Meta:
        abstract = True

    def get_user_permissions(self, obj=None):
        """
        Accounts does not assign permissions to a user,
         all permissions come through the permissions sets a user is a member of.
        """
        return set()

    def get_group_permissions(self, obj=None):
        """
        Returns a list of permission strings that this user has through their
        groups. This method queries all available auth backends. If an object
        is passed in, only permissions matching this object are returned.
        """
        permissions = set()
        for backend in auth.get_backends():
            if hasattr(backend, "get_group_permissions"):
                permissions.update(backend.get_group_permissions(self, obj))
        return permissions

    def get_all_permissions(self, obj=None):
        return self.get_group_permissions(obj)

    def has_perm(self, perm, obj=None):
        """
        Returns True if the user has the specified permission. This method
        queries all available auth backends, but returns immediately if any
        backend returns True. Thus, a user who has permission from a single
        auth backend is assumed to have permission in general. If an object is
        provided, permissions for this specific object are checked.
        """

        # Active superusers have all permissions.
        if self.is_active and self.is_superuser:
            return True

        # Otherwise we need to check the backends.
        for backend in auth.get_backends():
            if not hasattr(backend, 'has_perm'):
                continue
            try:
                if backend.has_perm(self, perm, obj):
                    return True
            except PermissionDenied:
                return False
        return False

    def has_perms(self, perm_list, obj=None):
        """
        Returns True if the user has each of the specified permissions. If
        object is passed, it checks if the user has all required perms for this
        object.
        """
        for perm in perm_list:
            if not self.has_perm(perm, obj):
                return False
        return True

    def has_module_perms(self, app_label):
        """
        Returns True if the user has any permissions in the given app label.
        Uses pretty much the same logic as has_perm, above.
        """
        # Active superusers have all permissions.
        if self.is_active and self.is_superuser:
            return True
        for backend in auth.get_backends():
            if not hasattr(backend, 'has_module_perms'):
                continue
            try:
                if backend.has_module_perms(self, app_label):
                    return True
            except PermissionDenied:
                return False
        return False

    def get_all_permission_sets(self, only_ids=False):
        """
        Returns all permission sets the user is member of AND all descendants
        sets of those sets.
        """
        direct_ps = self.permission_sets.all()
        all_ps = set()

        for ps in direct_ps:
            descendants = ps.get_descendants(include_self=True).all()
            for descendant in descendants:
                if only_ids:
                    all_ps.add(descendant.id)
                else:
                    all_ps.add(descendant)
        return all_ps


class AccountsAbstractUser(AbstractBaseUser, PermissionsMixin):
    """
    An abstract base class implementing a fully featured User model with
    admin-compliant permissions.

    Username and password are required. Other fields are optional.
    """
    username = models.CharField(
        _('username'),
        max_length=30,
        unique=True,
        help_text=_('Required. 30 characters or fewer. Letters, digits and @/./+/-/_ only.'),
        validators=[
            validators.RegexValidator(
                r'^[\w.@+-]+$',
                _('Enter a valid username. This value may contain only '
                  'letters, numbers ' 'and @/./+/-/_ characters.')
            ),
        ],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )
    first_name = models.CharField(_('first name'), max_length=30, blank=True)
    last_name = models.CharField(_('last name'), max_length=30, blank=True)
    email = models.EmailField(_('email address'), blank=True)
    phone = models.CharField(validators=[phone_regex], max_length=15, blank=True) # validators should be a list
    is_email_alert = models.BooleanField(
        _('email alert'),
        default=False,
        help_text=_('Should email alerts be sent to this user.'),
    )
    is_sms_alert = models.BooleanField(
        _('sms alert'),
        default=False,
        help_text=_('Should sms alerts be sent to this user.'),
    )
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into this admin site.'),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'phone']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        abstract = True

    def get_full_name(self):
        """
        Returns the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        "Returns the short name for the user."
        return self.first_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        """
        Sends an email to this User.
        """
        send_mail(subject, message, from_email, [self.email], **kwargs)


class User(AccountsAbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    class Meta(AbstractBaseUser.Meta):
        swappable = 'AUTH_USER_MODEL'
        verbose_name = _('user')
        verbose_name_plural = _('users')
