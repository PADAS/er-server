from django.core.exceptions import PermissionDenied
from django.conf.urls import url
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.forms import PasswordResetForm, UserCreationForm
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.utils.translation import ugettext_lazy as _
from django.utils.crypto import get_random_string
from django import forms
from utils.html import make_html_list
import django.contrib.auth.models

from accounts.models import User, PermissionSet


class PermissionSetAdminForm(forms.ModelForm):
    filter_horizontal = ('permissions', 'children')
    user_set = forms.ModelMultipleChoiceField(
        label='Users',
        queryset=User.objects.all(),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Users'),
            is_stacked=False
        )
    )

    class Meta:
        model = PermissionSet
        fields = ('name', 'permissions', 'children', 'user_set')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['user_set'].initial = self.instance.user_set.all()

    def _save_m2m(self):
        users = self.cleaned_data['user_set']
        self.instance.user_set.set(users)
        return super()._save_m2m()


@admin.register(PermissionSet)
class PermissionSetAdmin(DjangoGroupAdmin):
    form = PermissionSetAdminForm
    list_display = ('name', 'all_permissions', 'all_users')
    filter_horizontal = ('permissions', 'children')
    fieldsets = (
        (None, {
            'fields': ('name', 'permissions',
                       )}
         ),
        (_('Members'), {
            'fields': ('children', 'user_set')}),
    )

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'children':
            db_field.verbose_name = 'permission sets'
        return super().formfield_for_dbfield(db_field, **kwargs)

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


class CustomUserCreationForm(UserCreationForm):
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].required = False
        self.fields['password2'].required = False
        self.fields['password1'].widget.attrs['autocomplete'] = 'off'
        self.fields['password2'].widget.attrs['autocomplete'] = 'off'

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone',
                  'is_email_alert', 'is_sms_alert',
                  'username')

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get('password2')
        if password1 or password2:
            password2 = super().clean_password2()
        return password2


class UserAdmin(DjangoUserAdmin):
    ordering = ('last_name', 'first_name', 'username')
    fieldsets = (
        (None, {
            'fields': ('first_name', 'last_name',
                       'email', 'phone',
                       'is_email_alert', 'is_sms_alert',
                       'username', 'additional', 'password',
                       )}
         ),
        (_('Permissions'), {
            'fields': ('permission_sets', 'is_active', 'is_nologin', 'is_staff',
                       'is_superuser', 'act_as_profiles')}),
    )

    list_display = ('display_name', 'member_permission_sets',
                    'all_permission_sets', 'is_email_alert', 'is_sms_alert')
    list_editable = ('is_email_alert', 'is_sms_alert')
    list_display_links = ('display_name', )
    list_filter = ('is_staff', 'permission_sets')
    filter_horizontal = ('permission_sets',)

    add_form = CustomUserCreationForm
    add_fieldsets = (
        (None, {
            'fields': ('first_name', 'last_name',
                       'email', 'phone',
                       'is_email_alert', 'is_sms_alert',
                       'username', 'additional',
                       )}
         ),
        (_('Password'), {
            'description': (_('Optionally enter user\'s password,'
                              ' otherwise a password reset email is sent to the user')),
            'fields': ('password1', 'password2',)}),
        (_('Permissions'), {'fields': ('permission_sets',)}),
        (_('User Profiles'), {'fields': ('act_as_profiles',)}),
    )

    def display_name(self, instance):
        full_name = instance.get_full_name()
        if not full_name:
            full_name = instance.username
        return full_name

    def all_permission_sets(self, instance):
        pss = instance.get_all_permission_sets()
        display = '\n'.join(sorted(ps.name for ps in pss))
        return make_html_list(display)

    all_permission_sets.short_description = 'Effective Permission Sets'
    all_permission_sets.allow_tags = True

    def member_permission_sets(self, instance):
        pss = instance.permission_sets.all()
        display = '\n'.join(sorted(ps.name for ps in pss))
        return make_html_list(display)

    member_permission_sets.short_description = 'Member Permission Sets'
    member_permission_sets.allow_tags = True

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'act_as_profiles':
            queryset = User.objects.filter(is_staff=False)
            #queryset = queryset.filter(is_nologin=True)
            queryset = queryset.by_is_active()
            queryset = queryset.exclude(pk=request.user.pk)
            kwargs['queryset'] = queryset
        return super(UserAdmin, self).formfield_for_manytomany(db_field, request, **kwargs)

    def reset_password(self, request, user_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        user = get_object_or_404(self.model, pk=user_id)
        self.send_reset_email(request, user)
        return HttpResponseRedirect('..')

    def save_model(self, request, obj, form, change):
        if (not change and (not form.cleaned_data['password1']
                            or not obj.has_usable_password())):
            # Django's PasswordResetForm won't let us reset an unusable
            # password. We set it above super() so we don't have to save twice.
            obj.set_password(get_random_string())
            should_reset_password = True
        else:
            should_reset_password = False

        super(UserAdmin, self).save_model(request, obj, form, change)

        if should_reset_password:
            self.send_reset_email(request, obj)

    def send_reset_email(self, request, user):
        form = PasswordResetForm(data={'email': user.email})
        assert form.is_valid()

        opts = {
            'use_https': request.is_secure(),
            'request': request,
            'subject_template_name': 'registration/password_reset_subject.txt',
            'email_template_name': 'registration/password_reset_email.html',
        }

        form.save(**opts)

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
