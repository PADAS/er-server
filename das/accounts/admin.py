from __future__ import unicode_literals

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.utils.translation import ugettext_lazy as _
import django.contrib.auth.models
from django.contrib.auth.forms import UserChangeForm
from accounts.models import User, PermissionSet


class PermissionSetAdmin(DjangoGroupAdmin):
    pass


class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email', 'phone')}),
        (_('Alerting'), {'fields': ('is_email_alert', 'is_sms_alert')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'permission_sets')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )

    list_filter = ('is_staff', 'is_superuser', 'is_active', 'permission_sets')
    filter_horizontal = ('permission_sets',)



admin.site.register(User, UserAdmin)
if admin.site.is_registered(django.contrib.auth.models.Group):
    admin.site.unregister(django.contrib.auth.models.Group)
admin.site.register(PermissionSet, PermissionSetAdmin)