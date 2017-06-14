import uuid

from django.contrib import auth
from django.contrib.gis.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import JSONField
from django.utils.translation import ugettext_lazy as _
from django.core.mail import send_mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core import validators
from django.utils import timezone

from sendsms import api

from accounts.mixins import PermissionsMixin


phone_regex = validators.RegexValidator(
    regex=r'^\+?1?\d{9,15}$',
    message="Phone number must be entered in the format:  "
            "'+999999999'. Up to 15 digits allowed.")


class UserQuerySet(models.QuerySet):
    """Don't allow users to be deleted, set them as inactive"""
    def delete(self):
        self.update(active=False)

    def by_is_active(self, active=True):
        return self.filter(is_active=active)

    def _filter_or_exclude(self, mapper, *args, **kwargs):
        # 'name' is a field in your Model whose lookups you want case-insensitive by default
        if 'username' in kwargs:
            kwargs['username__iexact'] = kwargs['username']
            del kwargs['username']
        return super()._filter_or_exclude(mapper, *args, **kwargs)


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
    
    def get_queryset(self):
        return UserQuerySet(self.model, using=self._db)


def _user_has_module_perms(user, app_label):
    """
    A backend can raise `PermissionDenied` to short-circuit
    permission checking.
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
        help_text=_('Required. 30 characters or fewer.'
                    ' Letters, digits and @/./+/-/_ only.'),
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
    first_name = models.CharField(_('first name'), max_length=30)
    last_name = models.CharField(_('last name'), max_length=30)
    email = models.EmailField(_('email address'), unique=True)
    phone = models.CharField(validators=[phone_regex], max_length=15,
                             blank=True)  # validators should be a list
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
        help_text=_('Designates whether the user can log '
                    'into this admin site.'),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Set this False instead of deleting accounts.'
        ),
    )
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    additional = JSONField('additional data', default={}, null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'phone', 'last_name', 'first_name']

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
        """Returns the short name for the user."""
        return self.first_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        """
        Sends an email to this User.
        """
        send_mail(subject, message, from_email, [self.email], **kwargs)

    def send_sms(self, message, from_phone=None, **kwargs):
        """
        Sends an sms message to this User's cell phone if they have one
        """
        api.send_sms(body=message, from_phone=from_phone, to=[self.phone], **kwargs)


class User(AccountsAbstractUser):
    user_perms = {'accounts.view_user', 'accounts.change_user'}
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    class Meta(AbstractBaseUser.Meta):
        swappable = 'AUTH_USER_MODEL'
        verbose_name = _('user')
        verbose_name_plural = _('users')
        permissions = (
            ('view_user', "View a user's information."),
        )

    def get_user_permissions(self, obj=None):
        """
        A user can view and edit themselves
        """
        if obj and isinstance(obj, User) and self.id == obj.id:
            return super(User, self).get_user_permissions(obj)\
                   + self.user_perms

        return set()

    def delete(self, using=None, keep_parents=False):
        """Don't allow users to be deleted when they are referenced in
        other tables.
        """
        self.is_active = False
        self.save()

    def __str__(self):
        return self.get_username()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        result = super().clean()
        """case insensitive usernames"""
        try:
            user = User.objects.get_by_natural_key(self.username)
            if user.pk != self.pk:
                raise ValidationError(
                    {'username': ValidationError(
                    _('{0} already in use'.format(self.username)), code='invalid')})
        except User.DoesNotExist:
            pass

        return result