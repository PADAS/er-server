from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.widgets import FilteredSelectMultiple, RelatedFieldWidgetWrapper

from django.utils.translation import ugettext_lazy as _
from django.db.models import ManyToOneRel
from observations.models import Subject, SubjectGroup, SubjectSource

import logging
logger = logging.getLogger(__name__)

# class LoggingMixin(object):
#     def full_clean(self):
#         super(LoggingMixin, self).full_clean()
#         for field, errors in self.errors.items():
#             logger.info('Form error in %s: %s', ', '.join(errors))


class SubjectSourceForm(forms.ModelForm):
    def full_clean(self):
        super().full_clean()

    def clean(self):
        super().clean()

    class Meta:
        model = SubjectSource
        fields = ('id', 'subject', 'source', 'assigned_range', 'additional')


class JSONFieldFormMixin(object):

    json_field = "additional"

    def get_json(self):
        return getattr(self.instance, self.json_field)

    def __init__(self, *args, **kwargs):
        super(JSONFieldFormMixin, self).__init__(*args, **kwargs)
        if self.instance:
            json_data = self.get_json()
            for field in self.Meta.json_fields:
                if json_data.get(field):
                    self.fields[field].initial = json_data.get(field)

    def save(self, *args, **kwargs):
        json_data = self.get_json()
        for field in self.Meta.json_fields:
            json_data[field] = self.cleaned_data[field]
        setattr(self.instance, self.json_field, json_data)
        return super(JSONFieldFormMixin, self).save(*args, **kwargs)


from observations.models import SubjectSubType


class SubjectSubtypeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return '{}: {}'.format(obj.subject_type.display, obj.display)


class SubjectForm(forms.ModelForm):

    groups = forms.ModelMultipleChoiceField(
        queryset=SubjectGroup.objects.all(),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Groups'),
            is_stacked=False
        )
    )

    subject_subtype = SubjectSubtypeChoiceField(
        queryset=SubjectSubType.objects.all(),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['groups'].initial = self.instance.groups.all()

    class Meta:
        fields = '__all__'

    def _save_m2m(self):
        groups = self.cleaned_data['groups']
        self.instance.groups.set(groups)
        return super()._save_m2m()


from django import forms
from django.conf import settings
from django.utils.safestring import mark_safe


class ColorPickerWidget(forms.TextInput):
    '''
    This widget works closely with a customized version of bootstrap-colorpicker.
    '''
    class Media:
        css = {
            'all': (
                '/css/bootstrap-colorpicker.css',
            )
        }
        js = (
            '//code.jquery.com/jquery-3.2.1.js',
            '/js/bootstrap-colorpicker.js',
        )

    def __init__(self, language=None, attrs=None):
        self.language = language or settings.LANGUAGE_CODE[:2]
        super(ColorPickerWidget, self).__init__(attrs=attrs)

    def render(self, name, value, attrs=None):
        rendered = super(ColorPickerWidget, self).render(name, value, attrs)
        return rendered + mark_safe(
            '''<script type="text/javascript">
            $('#id_%s').colorpicker({format: 'rawrgb'});
            </script>''' % (name,)
        )


class SubjectFormWithAttributes(JSONFieldFormMixin, SubjectForm):
    '''
    This provides extra form fields for the attributes we expect to have stored in Subject.additional.
    '''
    rgb = forms.CharField(required=False, widget=ColorPickerWidget(), label='Color',
                          help_text=_('This is a color value in r,g,b format (ex. "100, 150, 102") for displaying the subject\'s tracks.'))
    sex = forms.ChoiceField(required=False, choices=(
        ('male', 'Male'), ('female', 'Female')))
    region = forms.CharField(
        required=False, help_text='This is the region that will be shown in the DAS Mobile App.')
    country = forms.CharField(
        required=False, help_text='This is the country that will be shown in the DAS Mobile App.')

    class Meta(SubjectForm.Meta):
        json_fields = ('rgb', 'sex', 'region', 'country')
        fields = ('name', 'subject_subtype',
                  'common_name', 'groups', json_fields)


class SubjectChangeListForm(forms.ModelForm):

    subject_subtype = SubjectSubtypeChoiceField(
        queryset=SubjectSubType.objects.all())

    class Meta:
        model = Subject
        fields = ('name', 'is_active')


class SetRandomColorForm(ActionForm):
    pass
