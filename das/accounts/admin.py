from django.core.exceptions import PermissionDenied
from django.conf.urls import patterns
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.contrib import admin
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.utils.translation import ugettext_lazy as _
import django.contrib.auth.models

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

    def reset_password(self, request, user_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        user = get_object_or_404(self.model, pk=user_id)

        form = PasswordResetForm(data={'email': user.email})
        form.is_valid()

        form.save(email_template_name='my_template.html')
        return HttpResponseRedirect('..')

    def get_urls(self):
        urls = super(UserAdmin, self).get_urls()
        my_urls = patterns('',
                           (r'^(\d+)/reset-password/$',
                            self.admin_site.admin_view(self.reset_password)
                            ),
                           )
        return my_urls + urls


admin.site.register(User, UserAdmin)
if admin.site.is_registered(django.contrib.auth.models.Group):
    admin.site.unregister(django.contrib.auth.models.Group)
admin.site.register(PermissionSet, PermissionSetAdmin)