from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.translation import ugettext_lazy as _

from observations.models import Subject, SubjectGroup


class SubjectForm(forms.ModelForm):

    groups = forms.ModelMultipleChoiceField(
        queryset=SubjectGroup.objects.all(),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Groups'),
            is_stacked=False
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['groups'].initial = self.instance.groups.all()

    # From the type/sub-type hierarchy above, build a Django form choice definition.
    TYPE_SUBTYPE_CHOICES = [
        (item['name'], tuple(('{0}:{1}'.format(item['value'], x), y) for (x, y) in item['subtypes'])) for item in
        Subject.TYPES_HIERARCHIES]

    SUBTYPE_FIELD = 'type_subtype_view'
    type_subtype_view = forms.ChoiceField(choices=TYPE_SUBTYPE_CHOICES, label='Subject Type')
    class Meta:
        fields = '__all__'
        exclude = ['subject_type', 'subject_subtype']

    def _save_m2m(self):
        groups = self.cleaned_data['groups']
        self.instance.groups.set(groups)
        return super()._save_m2m()
