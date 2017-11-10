import logging

from django.core.mail import EmailMultiAlternatives
import django.contrib.auth
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

import accounts

logger = logging.getLogger(__name__)

# This is a boiler-plate codename for the permission that will determine
# who gets a Source Report.
SOURCE_REPORT_PERMISSION_CODENAME = 'receive_source_report'


def send_report(subject='', to_email=None, text_content='', from_email=None, html_content=None):
    '''
    Send a message with optional HTML content.
    '''
    # Allow caller to provide a single address or a list.
    if isinstance(to_email, (str,)):
        to_email = [to_email]

    msg = EmailMultiAlternatives(
        subject=subject, body=text_content, from_email=from_email, to=to_email)
    if html_content:
        msg.attach_alternative(html_content, "text/html")

    msg.send()


def get_users_for_permission(permission_codename, usernames=None):
    User = django.contrib.auth.get_user_model()
    qs = User.objects.filter(
        is_active=True, permission_sets__permissions__codename=permission_codename)

    if usernames:
        qs = qs.filter(username__in=usernames)

    return qs


def create_report_permissionset():
    '''
    This should run once (probably as part of a migration) to add the proper permission and permissionset that
    will identify the users who receive reports.
    :return:
    '''
    User = django.contrib.auth.get_user_model()
    content_type = ContentType.objects.get_for_model(User)
    perm, created = django.contrib.auth.models.Permission.objects.get_or_create(
        codename=SOURCE_REPORT_PERMISSION_CODENAME,
        content_type=content_type,
        defaults=dict(name=_('Receive source report'),)
    )

    permission_set, created = accounts.models.PermissionSet.objects.get_or_create(
        name='Receive Source Report')
    permission_set.permissions.add(perm)
