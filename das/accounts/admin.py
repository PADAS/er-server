from oauth2_provider.admin import (AccessTokenAdmin, GrantAdmin,
                                   RefreshTokenAdmin)
from oauth2_provider.models import (get_access_token_model,
                                    get_application_model, get_grant_model,
                                    get_refresh_token_model)

import django.contrib.auth.models
from django import forms
from django.conf import settings
from django.conf.urls import re_path
from django.contrib import admin
from django.contrib.admin.widgets import (AdminDateWidget,
                                          FilteredSelectMultiple)
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import (PasswordResetForm, UserChangeForm,
                                       UserCreationForm)
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMultiAlternatives
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template import loader
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from accounts.models import PermissionSet, User
from accounts.utils import patrol_mgmt_permissions
from choices.models import Choice
from core.common import TIMEZONE_USED
from core.forms_utils import JSONFieldFormMixin
from observations import kmlutils
from utils.admin import DefaultFilterMixin
from utils.html import make_html_list

PATROL_ENABLED = settings.PATROL_ENABLED


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

    acquire_from = forms.ModelMultipleChoiceField(
        label='Permission Sets',
        queryset=PermissionSet.objects.all().order_by('name'),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Permission Sets'),
            is_stacked=False
        )
    )

    class Meta:
        model = PermissionSet
        fields = ('name', 'permissions', 'children', 'user_set', 'acquire_from',
                  )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['user_set'].initial = self.instance.user_set.all()
            self.fields['acquire_from'].initial = self.instance._parents.all()

        if not PATROL_ENABLED:
            self.fields['children'].queryset = self.fields['children'].queryset.\
                exclude(permissions__in=patrol_mgmt_permissions())

            self.fields['acquire_from'].queryset = self.fields['acquire_from'].queryset.\
                exclude(permissions__in=patrol_mgmt_permissions())

            self.fields['permissions'].queryset = self.fields['permissions'].queryset.\
                exclude(
                    codename__in=patrol_mgmt_permissions().values_list('codename'))

        self.fields['permissions'].queryset = self.fields['permissions'].queryset. \
            exclude(codename__in=patrol_mgmt_permissions(modelnames=('patrolsegment',
                                                                     'patrolnote', 'patrolfile',
                                                                     'patrolsegmentmembership')).values_list('codename'))

    def _save_m2m(self):
        users = self.cleaned_data['user_set']
        inherit_from = self.cleaned_data['acquire_from']
        self.instance.user_set.set(users)
        self.instance._parents.set(inherit_from)
        return super()._save_m2m()


@admin.register(PermissionSet)
class PermissionSetAdmin(DjangoGroupAdmin):
    form = PermissionSetAdminForm
    list_display = ('name', 'all_permissions', 'all_users')
    ordering = ('name',)
    filter_horizontal = ('permissions', 'children')
    fieldsets = (
        (None, {
            'fields': ('name', 'permissions',
                       )}
         ),
        (_('Acquire permissions from'), {
            'fields': ('acquire_from', )
        }),
        (_('Grant permissions to'), {
            'fields': ('children', 'user_set')}),
    )

    def get_queryset(self, request):
        queryset = super(PermissionSetAdmin, self).get_queryset(request)
        if not PATROL_ENABLED:
            return queryset.exclude(permissions__in=patrol_mgmt_permissions())
        return queryset

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'children':
            db_field.verbose_name = 'Permission Sets'
        return super().formfield_for_dbfield(db_field, **kwargs)

    def all_permissions(self, instance):
        permissions = instance.permissions.all()
        return make_html_list(sorted(ps.name for ps in permissions))

    all_permissions.short_description = 'Permissions'
    all_permissions.allow_tags = True

    def all_users(self, instance):
        users = instance.user_set.all()
        return make_html_list(sorted(u.get_full_name() for u in users))

    all_users.short_description = 'Users'
    all_users.allow_tags = True

    class Media:
        css = {
            'all': ('css/resize_multipleselect_widget.css',),
        }


ROLE_CHOICES = [('', 'Select One'),
                ('community-liaison-officer', _('Community Liaison Officer')),
                ('community-manager', _('Community Manager')),
                ("deployment-partner", _("EarthRanger Deployment Partner")),
                ('ecologist-scientist', _('Ecologist / Scientist')),
                ('ecology-manager', _('Ecology Manager')),
                ('gis-engineer', _('GIS Engineer')),
                ('hwc-liaison', _('HWC Liaison')),
                ('hwc-officer', _('HWC Officer')),
                ('it-admin-tech-support', _('IT Admin / Tech Support')),
                ('operations-coordinator', _('Operations Coordinator')),
                ('operations-manager', _('Operations Manager')),
                ('protected-area-manager', _('Protected Area Manager')),
                ('security-manager', _('Security Manager')),
                ("support-team", _("EarthRanger Support Team")),
                ('tech-partner', _('Tech Partner')),
                ]


class CustomUserCreationForm(JSONFieldFormMixin, UserCreationForm):
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(required=False)

    # Additional JSON Fields
    notes = forms.CharField(
        required=False, label='Notes', widget=forms.Textarea)
    expiry = forms.DateTimeField(required=False, label='Expiry',
                                 widget=AdminDateWidget())
    moudatesigned = forms.DateTimeField(
        required=False, label='MoU Date Signed', widget=AdminDateWidget())
    moutype = forms.CharField(required=False, label='MoU Type')
    moufilename = forms.CharField(required=False, label='MoU Filename')
    tech = forms.TypedMultipleChoiceField(widget=FilteredSelectMultiple(
        verbose_name='Tech Choices', is_stacked=False), required=False)
    organization = forms.ChoiceField(required=False,
                                     help_text='User Organization')
    role = forms.ChoiceField(required=False, label="Role",
                             choices=ROLE_CHOICES)

    @staticmethod
    def fetch_tech_choices():
        # Fetch all Tech choices from choices.Choice Model. For Ex: iOS, GE etc
        tech_choices = {'': ''}
        for tech in Choice.objects.filter(
                model='accounts.user.User', field='tech').order_by('ordernum'):
            tech_choices[tech.value] = tech.display
        return tuple([(key, value) for key, value in tech_choices.items()])

    @staticmethod
    def fetch_organization_choices():
        # Fetch all Organization choices from choices.Choice Model.
        organization_choices = {'': ''}
        for organization in Choice.objects.filter(
                model='accounts.user.User', field='organization') \
                .order_by('ordernum'):
            organization_choices[organization.value] = organization.display
        return tuple(
            [(key, value) for key, value in organization_choices.items()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].required = False
        self.fields['password2'].required = False
        self.fields['password1'].widget.attrs['autocomplete'] = 'off'
        self.fields['password2'].widget.attrs['autocomplete'] = 'off'
        self.fields['tech'].choices = self.fetch_tech_choices()
        self.fields['organization'].choices = self.fetch_organization_choices()

    class Meta:
        model = User
        json_fields = ('notes', 'expiry', 'moudatesigned', 'moutype', 'moufilename',
                       'organization', 'tech', 'role')
        fields = ('first_name', 'last_name', 'email',
                  'phone', 'username') + json_fields

    json_field = 'additional'

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get('password2')
        if password1 or password2:
            password2 = super().clean_password2()
        return password2

    def clean_email(self):
        # Set email value as None rather than blank string.
        # In comparison Blank string is considered as Unique.
        email = self.cleaned_data.get("email")
        if email.strip() == '':
            return None
        return email


class UserAdditionalForm(JSONFieldFormMixin, UserChangeForm):
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(required=False)

    # Additional JSON Fields
    notes = forms.CharField(
        required=False, label='Notes', widget=forms.Textarea)
    expiry = forms.DateTimeField(required=False, label=_(
        'MoU Expires'), widget=AdminDateWidget())
    moudatesigned = forms.DateTimeField(
        required=False, label='MoU Date Signed', widget=AdminDateWidget())
    moutype = forms.CharField(required=False, label='MoU Type')
    moufilename = forms.CharField(required=False, label='MoU Filename')
    tech = forms.TypedMultipleChoiceField(widget=FilteredSelectMultiple(
        verbose_name='Tech Choices', is_stacked=False), required=False)
    organization = forms.ChoiceField(required=False,
                                     help_text='User Organization')
    role = forms.ChoiceField(required=False, label="Role",
                             choices=ROLE_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tech'].choices = CustomUserCreationForm.fetch_tech_choices()
        self.fields['organization'].choices = CustomUserCreationForm.fetch_organization_choices()

    class Meta:
        model = User
        json_fields = ('notes', 'expiry', 'moudatesigned', 'moutype', 'moufilename',
                       'organization', 'tech', 'role')
        json_date_fields = ('expiry', 'moudatesigned')
        fields = ('first_name', 'last_name', 'email',
                  'phone', 'username') + json_fields

    json_field = 'additional'

    def clean_email(self):
        # Set email value as None rather than blank string.
        # In comparison Blank string is considered as Unique.
        email = self.cleaned_data.get("email")
        if email.strip() == '':
            return None
        return email


class KmkMasterLinkForm(forms.Form):
    email = forms.EmailField(label=_("Email"), max_length=254)

    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        """
        Sends a django.core.mail.EmailMultiAlternatives to `to_email`.
        """
        subject = loader.render_to_string(subject_template_name, context)
        # Email subject *must not* contain newlines
        subject = ''.join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)

        email_message = EmailMultiAlternatives(
            subject, body, from_email, [to_email])
        if html_email_template_name is not None:
            html_email = loader.render_to_string(
                html_email_template_name, context)
            email_message.attach_alternative(html_email, 'text/html')

        email_message.send()

    def save(self, user=None, subject_template_name='registration/kml_master_link_subject.txt',
             email_template_name='registration/kml_master_link_email.html',
             from_email=None, request=None, html_email_template_name=None):

        context = {
            'kml_master_link': kmlutils.get_kml_master_link(user, request),
            'site_name': get_current_site(request).name
        }
        self.send_mail(subject_template_name, email_template_name, context,
                       from_email, user.email, html_email_template_name)


class UserAdmin(DefaultFilterMixin, DjangoUserAdmin):
    readonly_fields = ('_last_login',)
    ordering = ('username', 'last_name', 'first_name',)
    fieldsets = (
        (None, {
            'fields': ('first_name', 'last_name', 'role',
                       'email', 'phone',
                       'username', 'password', '_last_login',)
        }),
        ('Advanced Attributes', {
            'classes': ('collapse',),
            'fields': ('notes', 'expiry', 'moudatesigned', 'moutype', 'moufilename',
                       'organization', 'tech',)
        }),
        ('Additional Data', {
            'fields': ['additional']}
         ),
        (_('Permissions'), {
            'fields': ('permission_sets', 'is_active', 'is_nologin', 'is_staff',
                       'is_superuser', 'act_as_profiles')}),
    )

    list_display = ('display_name', 'username', '_last_login', 'member_permission_sets',
                    'all_permission_sets', 'is_active')
    list_editable = ('is_active',)
    list_display_links = ('display_name', )
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'permission_sets')
    filter_horizontal = ('permission_sets',)
    form = UserAdditionalForm
    add_form = CustomUserCreationForm
    add_fieldsets = (
        (None, {
            'fields': ('first_name', 'last_name', 'role',
                       'email', 'phone',
                       'username'
                       )
        }),
        ('Advanced Attributes', {
            'classes': ('collapse',),
            'fields': ('notes', 'expiry', 'moudatesigned', 'moutype', 'moufilename',
                       'organization', 'tech',)
        }),
        ('Additional JSON Data', {
            'fields': ['additional']
        }),
        (_('Password'), {
            'description': (_('Optionally enter user\'s password,'
                              ' otherwise a password reset email is sent to the'
                              ' user')),
            'fields': ('password1', 'password2',)}),
        (_('Permissions'), {'fields': ('permission_sets', 'is_active',
                                       'is_nologin', 'is_staff',
                                       'is_superuser')}),
        (_('User Profiles'), {'fields': ('act_as_profiles',)}),
    )

    def get_default_filters(self, request):
        return {
            'is_active__exact': 1,
        }

    def display_name(self, instance):
        full_name = instance.get_full_name()
        if not full_name:
            full_name = instance.username
        return full_name
    display_name.admin_order_field = 'username'

    def all_permission_sets(self, instance):
        pss = instance.get_all_permission_sets()
        return make_html_list(sorted(ps.name for ps in pss))

    all_permission_sets.short_description = 'Effective Permission Sets'
    all_permission_sets.allow_tags = True

    def member_permission_sets(self, instance):
        pss = instance.permission_sets.all()
        return make_html_list(sorted(ps.name for ps in pss))

    member_permission_sets.short_description = 'Member Permission Sets'
    member_permission_sets.allow_tags = True

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # TODO: for a user with is_nologin set, do not return a set of profiles
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

        if user.email:
            self.send_reset_email(request, user)
        return HttpResponseRedirect('..')

    def get_kml_master_link(self, request, user_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        user = get_object_or_404(self.model, pk=user_id)
        if user.email:
            self.send_kml_email(request, user)
        return HttpResponseRedirect('..')

    def save_model(self, request, obj, form, change):
        if (not change and (not form.cleaned_data['password1']
                            or not obj.has_usable_password())):
            # Django's PasswordResetForm won't let us reset an unusable
            # password. We set it above super() so we don't have to save twice.
            obj.set_password(get_random_string(length=12))
            should_reset_password = True
        else:
            should_reset_password = False

        super(UserAdmin, self).save_model(request, obj, form, change)

        if should_reset_password and obj.email:
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

    def send_kml_email(self, request, user):
        form = KmkMasterLinkForm(data={'email': user.email})
        assert form.is_valid()

        opts = {
            'request': request,
            'user': user,
            'subject_template_name': 'utility/kml_master_link_subject.txt',
            'email_template_name': 'utility/kml_master_link_email.html',
        }

        form.save(**opts)

    def get_urls(self):
        urls = super(UserAdmin, self).get_urls()
        my_urls = [
            re_path(
                r"^(.+)/change/reset-password/?$",
                self.admin_site.admin_view(self.reset_password),
            ),
            re_path(
                r"^(.+)/change/get-kml-link/?$",
                self.admin_site.admin_view(self.get_kml_master_link),
            ),
        ]
        return [*my_urls, *urls]

    def _last_login(self, instance):
        return instance.last_login if instance.last_login else 'Never Logged in'

    _last_login.short_description = _('Last Login In %s' % TIMEZONE_USED)
    _last_login.admin_order_field = 'last_login'


admin.site.register(User, UserAdmin)
if admin.site.is_registered(django.contrib.auth.models.Group):
    admin.site.unregister(django.contrib.auth.models.Group)


class AccessGrantForm(forms.ModelForm):
    class Meta:
        labels = {'expires': f'Expires in {TIMEZONE_USED}'}


class RefreshForm(forms.ModelForm):
    class Meta:
        labels = {'revoked': f'Revoked in {TIMEZONE_USED}'}


class GrantAdmin(admin.ModelAdmin):
    form = AccessGrantForm
    list_display = ("code", "application", "user", "expires")
    ordering = list_display
    raw_id_fields = ("user", )

    def _expires(self, o):
        return o.expires
    _expires.short_description = 'expires in %s' % TIMEZONE_USED
    _expires.admin_order_field = 'expires'


class AccessTokenAdmin(admin.ModelAdmin):
    form = AccessGrantForm
    list_display = ("token", "user", "application", "_expires")
    ordering = ("token", "user", "application", "expires")
    raw_id_fields = ("user", )
    search_fields = ('user__username', 'token',)

    def _expires(self, o):
        return o.expires
    _expires.short_description = 'expires in %s' % TIMEZONE_USED
    _expires.admin_order_field = 'expires'


class RefreshTokenAdmin(admin.ModelAdmin):
    form = RefreshForm
    list_display = ("token", "user", "application", '_revoked')
    ordering = ("token", "user", "application", "revoked")
    raw_id_fields = ("user", "access_token")

    def _revoked(self, o):
        return o.revoked
    _revoked.short_description = 'Revoked in %s' % TIMEZONE_USED
    _revoked.admin_order_field = 'revoked'


Application = get_application_model()
Grant = get_grant_model()
AccessToken = get_access_token_model()
RefreshToken = get_refresh_token_model()

# AccessToken
admin.site.unregister(AccessToken)
admin.site.register(AccessToken, AccessTokenAdmin)

# Grant
admin.site.unregister(Grant)
admin.site.register(Grant, GrantAdmin)

# Refresh
admin.site.unregister(RefreshToken)
admin.site.register(RefreshToken, RefreshTokenAdmin)
