import logging

from django.contrib import admin, messages
from django.contrib.admin.actions import delete_selected
from django.contrib.admin.templatetags.admin_modify import *
from django.contrib.admin.templatetags.admin_modify import \
    submit_row as original_submit_row
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import model_ngettext
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.safestring import mark_safe

import choices.models as models
from choices.forms import ChoiceForm
import urllib.parse as urlparse
from urllib.parse import urlencode, quote


@admin.register(models.Choice)
class ChoiceAdmin(admin.ModelAdmin):
    change_list_template = "admin/disable_change_list.html"
    delete_confirmation_template = "admin/soft_delete_confirmation.html"
    delete_selected_confirmation_template = "admin/soft_delete_selected_confirmation.html"

    form = ChoiceForm
    actions = ('disable_choices', )
    ordering = ('model', 'field', 'value', 'display', 'ordernum', 'is_active')
    list_display = ('model', 'field', 'value', 'display', 'ordernum',
                    '_icon_display', 'is_active')
    list_display_links = ('model', 'field')
    search_fields = ('model', 'field', 'value', 'display')
    list_filter = ('model', 'field')
    list_editable = ('value', 'display', 'ordernum')
    exclude = ('delete_on', 'is_active')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.filter_active_choices()
        if not self.has_change_permission(request):
            queryset = queryset.none()
        return queryset

    def get_changeform_initial_data(self, request):
        if request.GET:
            return {
                'model': request.GET.get('model'),
                'field': request.GET.get('field')
            }
        super().get_changeform_initial_data(request)

    def pass_params_to_url(self, redirect_url, params):
        url_parts = list(urlparse.urlparse(redirect_url))
        url_parts[4] = urlencode(params)
        return urlparse.urlunparse(url_parts)

    def addvalue(self, request, obj, opts, action, url):
        self.message_user(
            request,
            _('The {name} "{obj}" was {action} successfully. You may add another {name} below.'.format(
                name=opts.verbose_name, obj=str(obj), action=action)),
            messages.SUCCESS)

        preserved_filters = self.get_preserved_filters(request)
        redirect_url = add_preserved_filters(
            {'preserved_filters': preserved_filters, 'opts': opts}, url)

        params = {'model': obj.model, 'field': obj.field}
        redirect_url = self.pass_params_to_url(redirect_url, params)
        return HttpResponseRedirect(redirect_url)

    def response_add(self, request, obj, post_url_continue=None):
        if "_addvalue" in request.POST:
            opts = obj._meta
            return self.addvalue(request, obj, opts, 'added', request.path)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_addvalue" in request.POST:
            opts = self.model._meta
            redirect_url = reverse('admin:%s_%s_add' %
                                   (opts.app_label, opts.model_name),
                                   current_app=self.admin_site.name)
            return self.addvalue(request, obj, opts, 'changed', redirect_url)
        return super().response_change(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        if 'disable_choices' in request.POST:

            opts = self.model._meta
            self.message_user(
                request,
                _('The {name} "{object}" was disabled.'.format(
                    name=opts.verbose_name, object=obj_display)),
                messages.WARNING)

            if self.has_change_permission(request, None):
                post_url = reverse('admin:%s_%s_changelist' %
                                   (opts.app_label, opts.model_name),
                                   current_app=self.admin_site.name)
                preserved_filters = self.get_preserved_filters(request)
                post_url = add_preserved_filters(
                    {
                        'preserved_filters': preserved_filters,
                        'opts': opts
                    }, post_url)

                return HttpResponseRedirect(post_url)
            else:
                post_url = reverse('admin:index',
                                   current_app=self.admin_site.name)
                return HttpResponseRedirect(post_url)
        return super().response_delete(request, obj_display, obj_id)

    def delete_disable_selected(self, modeladmin, request, queryset):
        delete = queryset.delete
        count = queryset.count
        message = modeladmin.message_user

        def _delete_closure():
            """
            Wraps the original delete method which gets called by
            delete_selected()
            """
            if 'disable_choices' in request.POST:
                fmt = 'Successfully disabled {0} {1}.'
                messages.add_message(
                    request, messages.WARNING,
                    fmt.format(len(queryset), self.opts.verbose_name))
                result = queryset.soft_delete()
            else:
                fmt = _("Successfully deleted {count} {items}s.")
                messages.add_message(
                    request, messages.SUCCESS,
                    fmt.format(count=count(),
                               items=model_ngettext(modeladmin.opts, count())))
                result = delete()

            return result

        def _message(request, message, message_level):
            pass

        queryset.delete = _delete_closure
        modeladmin.message_user = _message
        return delete_selected(modeladmin, request, queryset)

    def get_actions(self, request):
        """Patch delete_selected to have our method running"""
        actions = super().get_actions(request)
        actions['delete_selected'] = (self.delete_disable_selected,
                                      'delete_selected',
                                      delete_selected.short_description)
        return actions

    def delete_model(self, request, obj):
        if 'disable_choices' in request.POST:
            return obj.disable()

        super().delete_model(request, obj)

    def disable_choices(self, request, queryset):
        fmt = 'Successfully disabled {0} {1}.'
        self.message_user(request,
                          fmt.format(len(queryset), self.opts.verbose_name),
                          messages.WARNING)
        return queryset.disable_choices()

    disable_choices.short_description = "Disable selected choices"

    def _icon_display(self, obj):
        url = models.Choice.marker_icon(obj.icon_id)
        return mark_safe(
            f'<img src="{url}" style="height:2.5em; filter:opacity(0.8)" />')


@admin.register(models.DisableChoice)
class DisableChoiceAdmin(admin.ModelAdmin):
    # actions = ('disable_choices', )
    ordering = ('model', 'field', 'ordernum', 'display', 'delete_on')
    list_display = ('model', 'field', 'value', 'display', 'ordernum',
                    'delete_on', 'is_active')
    list_display_links = ('model', 'field')
    search_fields = ('model', 'field', 'value', 'display')
    list_editable = ('value', 'display', 'ordernum', 'is_active')
    list_filter = ('value', 'delete_on', 'field')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.filter_inactive_choices()
        if not self.has_change_permission(request):
            queryset = queryset.none()
        return queryset

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if change and obj.is_active:
            obj.delete_on = None
        super().save_model(request, obj, form, change)


@admin.register(models.DynamicChoice)
class DynamicChoiceAdmin(admin.ModelAdmin):
    ordering = ('id', 'model_name')
    list_display = ('id', 'model_name', 'criteria')
    list_display_links = ('id',)
    search_fields = ('model_name',)
