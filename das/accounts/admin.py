from __future__ import unicode_literals

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.utils.translation import ugettext_lazy as _
import django.contrib.auth.models
from django.contrib.auth.forms import UserChangeForm
from mptt.admin import MPTTModelAdmin
from mptt.forms import TreeNodeMultipleChoiceField
from accounts.models import User, PermissionSet


class PermissionSetMPTTModelAdmin(MPTTModelAdmin):
    search_fields = ('name',)
    ordering = ('name',)
    filter_horizontal = ('permissions',)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == 'permissions':
            qs = kwargs.get('queryset', db_field.remote_field.model.objects)
            # Avoid a major performance hit resolving permission names which
            # triggers a content_type load:
            kwargs['queryset'] = qs.select_related('content_type')
        return super(PermissionSetMPTTModelAdmin, self).formfield_for_manytomany(
            db_field, request=request, **kwargs)

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

class UserWithMPTTChangeForm(UserChangeForm):
    permission_sets = TreeNodeMultipleChoiceField(queryset=PermissionSet.objects.all())

class UserWithMPTTAdmin(UserAdmin):
    form = UserWithMPTTChangeForm



admin.site.register(User, UserWithMPTTAdmin)
if admin.site.is_registered(django.contrib.auth.models.Group):
    admin.site.unregister(django.contrib.auth.models.Group)
admin.site.register(PermissionSet, PermissionSetMPTTModelAdmin)