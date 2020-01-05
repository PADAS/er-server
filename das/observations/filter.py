import pytz
import django
import datetime
from collections import OrderedDict
from django import forms
from django.templatetags.static import StaticNode
from django.utils import timezone
from django.conf import settings
from django.contrib.admin.widgets import AdminDateWidget, AdminSplitDateTime as BaseAdminSplitDateTime
from django.utils.encoding import force_str
from django.template.defaultfilters import slugify

from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

# class DateRangeFilter(admin.filters.FieldListFilter):
#     template = 'admin/daterange_filter.html'

#     def __init__(self, field, request, params, model, model_admin, field_path):
#         self.lookup_kwarg_gte = '{0}__range__gte'.format(field_path)
#         self.lookup_kwarg_lte = '{0}__range__lte'.format(field_path)

#         super(DateRangeFilter, self).__init__(field, request, params, model, model_admin, field_path)
#         self.request = request
#         self.form = self.get_form(request)

#     def get_timezone(self, request):
#         return timezone.get_default_timezone()

#     def choices(self, cl):
#         yield {
#             # slugify converts any non-unicode characters to empty characters
#             # but system_name is required, if title converts to empty string use id
#             # https://github.com/silentsokolov/django-admin-rangefilter/issues/18
#             'system_name':
#             force_str(
#                 slugify(self.title) if slugify(self.title) else id(self.title)
#             ),
#             'query_string':
#             cl.get_query_string({}, remove=self._get_expected_fields())
#         }

#     @staticmethod
#     def make_dt_aware(value, timezone):
#         if settings.USE_TZ and pytz is not None:
#             default_tz = timezone
#             if value.tzinfo is not None:
#                 value = default_tz.normalize(value)
#             else:
#                 value = default_tz.localize(value)
#         return value

#     def expected_parameters(self):
#         return self._get_expected_fields()

#     def _get_expected_fields(self):
#         return [self.lookup_kwarg_gte, self.lookup_kwarg_lte]

#     def queryset(self, request, queryset):
#         if self.form.is_valid():
#             validated_data = dict(self.form.cleaned_data.items())
#             if validated_data:
#                 return queryset.filter(**self._make_query_filter(request, validated_data))

#     def _make_query_filter(self, request, validated_data):
#         query_params = {}
#         date_value_gte = validated_data.get(self.lookup_kwarg_gte, None)
#         date_value_lte = validated_data.get(self.lookup_kwarg_lte, None)

#         if date_value_gte:
#             query_params['{0}__gte'.format(self,field_path)] = self.make_dt_aware(
#                 datetime.combine(date_value_gte, datetime.time.min),
#                 self.get_timezone(request)
#             )
#         return query_params

#     def get_form(self, request):
#         form_class = self._get_form_class()
#         return form_class(self.used_parameters)

#     def _get_form_class(self):
#         fields = self._get_form_fields()

#         form_class = type(str('DateRangeForm'), (forms.BaseForm, ),
#                           {'base_fields': fields})

#         form_class.media = self._get_media()
#         # lines below ensure that the js static files are loaded just once
#         # even if there is more than one DateRangeFilter in use
#         request_key = 'DJANGO_RANGEFILTER_ADMIN_JS_SET'
#         # if (getattr(self.request, request_key, False)):
#         #     form_class.js = []
#         # else:
#         setattr(self.request, request_key, True)
#         form_class.js = self.get_js()
#         return form_class

#     def _get_form_fields(self):
#         return OrderedDict(
#             ((self.lookup_kwarg_gte,
#                 forms.DateField(label='',
#                                 widget=AdminDateWidget(
#                                     attrs={'placeholder': _('From date')}),
#                                 localize=True,
#                                 required=False)),
#                 (self.lookup_kwarg_lte,
#                 forms.DateField(label='',
#                                 widget=AdminDateWidget(
#                                     attrs={'placeholder': _('To date')}),
#                                 localize=True,
#                                 required=False))))

#     @staticmethod
#     def _get_media():
#         js = [
#             'calendar.js',
#             'admin/DateTimeShortcuts.js'
#         ]
#         css = [
#             'widget.css'
#         ]
#         return forms.Media(
#             js=['admin/js/%s' % url for url in js],
#             css={'all': ['admin/css/%s' % path for path in css]})

#     @staticmethod
#     def get_js():
#         return [
#             StaticNode.handle_simple('admin/js/calendar.js'),
#             StaticNode.handle_simple('admin/js/admin/DateTimeShortcuts.js'),
#         ]


class DateRangeFilter(admin.filters.FieldListFilter):
    def __init__(self, field, request, params, model, model_admin, field_path):
        self.lookup_kwarg_gte = '{0}__range__gte'.format(field_path)
        self.lookup_kwarg_lte = '{0}__range__lte'.format(field_path)

        super(DateRangeFilter, self).__init__(field, request, params, model,
                                              model_admin, field_path)
        self.request = request
        self.form = self.get_form(request)

    def get_timezone(self, request):
        return timezone.get_default_timezone()

    @staticmethod
    def make_dt_aware(value, timezone):
        if settings.USE_TZ and pytz is not None:
            default_tz = timezone
            if value.tzinfo is not None:
                value = default_tz.normalize(value)
            else:
                value = default_tz.localize(value)
        return value

    def choices(self, cl):
        yield {
            # slugify converts any non-unicode characters to empty characters
            # but system_name is required, if title converts to empty string use id
            # https://github.com/silentsokolov/django-admin-rangefilter/issues/18
            'system_name':
            force_str(
                slugify(self.title) if slugify(self.title) else id(self.title)
            ),
            'query_string':
            cl.get_query_string({}, remove=self._get_expected_fields())
        }

    def expected_parameters(self):
        return self._get_expected_fields()

    def queryset(self, request, queryset):
        if self.form.is_valid():
            validated_data = dict(self.form.cleaned_data.items())
            if validated_data:
                return queryset.filter(
                    **self._make_query_filter(request, validated_data))
        return queryset

    def _get_expected_fields(self):
        return [self.lookup_kwarg_gte, self.lookup_kwarg_lte]

    def _make_query_filter(self, request, validated_data):
        query_params = {}
        date_value_gte = validated_data.get(self.lookup_kwarg_gte, None)
        date_value_lte = validated_data.get(self.lookup_kwarg_lte, None)

        if date_value_gte:
            query_params['{0}__gte'.format(
                self.field_path)] = self.make_dt_aware(
                    datetime.datetime.combine(date_value_gte,
                                              datetime.time.min),
                    self.get_timezone(request),
                )
        if date_value_lte:
            query_params['{0}__lte'.format(
                self.field_path)] = self.make_dt_aware(
                    datetime.datetime.combine(date_value_lte,
                                              datetime.time.max),
                    self.get_timezone(request),
                )

        return query_params

    def get_template(self):
        return 'admin/daterange_filter.html'

    template = 'admin/daterange_filter.html'

    def get_form(self, request):
        form_class = self._get_form_class()
        return form_class(self.used_parameters)

    def _get_form_class(self):
        fields = self._get_form_fields()

        form_class = type(str('DateRangeForm'), (forms.BaseForm, ),
                          {'base_fields': fields})
        form_class.media = self._get_media()
        # lines below ensure that the js static files are loaded just once
        # even if there is more than one DateRangeFilter in use
        # request_key = 'DJANGO_RANGEFILTER_ADMIN_JS_SET'
        # if (getattr(self.request, request_key, False)):
        #     form_class.js = []
        # else:
        # setattr(self.request, request_key, True)
        form_class.js = self.get_js()
        return form_class

    def _get_form_fields(self):
        return OrderedDict((
            (self.lookup_kwarg_gte,
             forms.DateField(
                 label='',
                 widget=AdminDateWidget(attrs={'placeholder': _('From date')}),
                 localize=True,
                 required=False)),
            (self.lookup_kwarg_lte,
             forms.DateField(
                 label='',
                 widget=AdminDateWidget(attrs={'placeholder': _('To date')}),
                 localize=True,
                 required=False)),
        ))

    @staticmethod
    def get_js():
        return [
            StaticNode.handle_simple('admin/js/calendar.js'),
            StaticNode.handle_simple('admin/js/admin/DateTimeShortcuts.js'),
        ]

    @staticmethod
    def _get_media():
        js = [
            'calendar.js',
            'admin/DateTimeShortcuts.js',
        ]
        css = [
            'widgets.css',
        ]
        return forms.Media(
            js=['admin/js/%s' % url for url in js],
            css={'all': ['admin/css/%s' % path for path in css]})
