from django.core.exceptions import PermissionDenied
from django.conf.urls import url
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.contrib import admin
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.utils.translation import ugettext_lazy as _
from utils.html import make_html_list
import django.contrib.auth.models

from accounts.models import User, PermissionSet


class PermissionSetAdmin(DjangoGroupAdmin):
    list_display = ('name', 'all_permissions', 'all_users')
    filter_horizontal = ('permissions', 'children')

    def all_permissions(self, instance):
        permissions = instance.permissions.all()
        display = '\n'.join((permission.name for permission in permissions))
        return make_html_list(display)

    all_permissions.short_description = 'Permissions'
    all_permissions.allow_tags = True

    def all_users(self, instance):
        users = instance.user_set.all()
        display = '\n'.join((user.get_full_name() for user in users))
        return make_html_list(display)

    all_users.short_description = 'Users'
    all_users.allow_tags = True


class UserAdmin(DjangoUserAdmin):
    ordering = ('last_name', 'first_name', 'username')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email', 'phone')}),
        (_('Alerting'), {'fields': ('is_email_alert', 'is_sms_alert')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'permission_sets')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )

    list_display = ('display_name', 'member_permission_sets',
                    'all_permission_sets', 'is_email_alert', 'is_sms_alert')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'permission_sets')
    filter_horizontal = ('permission_sets',)

    def display_name(self, instance):
        full_name = instance.get_full_name()
        if not full_name:
            full_name = instance.username
        return full_name

    def all_permission_sets(self, instance):
        pss = instance.get_all_permission_sets()
        display = '\n'.join(sorted(ps.name for ps in pss))
        return make_html_list(display)

    all_permission_sets.short_description = 'All Permission Sets'
    all_permission_sets.allow_tags = True

    def member_permission_sets(self, instance):
        pss = instance.permission_sets.all()
        display = '\n'.join(sorted(ps.name for ps in pss))
        return make_html_list(display)

    member_permission_sets.short_description = 'Member Permission Sets'
    member_permission_sets.allow_tags = True

    def reset_password(self, request, user_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        user = get_object_or_404(self.model, pk=user_id)

        form = PasswordResetForm(data={'email': user.email})
        form.is_valid()

        opts = {
            'use_https': request.is_secure(),
            'request': request,
            'email_template_name': 'registration/password_reset_email.html',
        }

        form.save(**opts)
        return HttpResponseRedirect('..')

    def get_urls(self):
        urls = super(UserAdmin, self).get_urls()
        my_urls = [url(r'^(.+)/change/reset-password/?$',
                   self.admin_site.admin_view(self.reset_password)
                   ),
                   ]
        return my_urls + urls


admin.site.register(User, UserAdmin)
if admin.site.is_registered(django.contrib.auth.models.Group):
    admin.site.unregister(django.contrib.auth.models.Group)
admin.site.register(PermissionSet, PermissionSetAdmin)