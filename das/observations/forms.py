from django import forms
from observations.models import Subject


class SubjectForm(forms.ModelForm):

    # From the type/sub-type hierarchy above, build a Django form choice definition.
    TYPE_SUBTYPE_CHOICES = [
        (item['name'], tuple(('{0}:{1}'.format(item['value'], x), y) for (x, y) in item['subtypes'])) for item in
        Subject.TYPES_HIERARCHIES]

    SUBTYPE_FIELD = 'type_subtype_view'
    type_subtype_view = forms.ChoiceField(choices=TYPE_SUBTYPE_CHOICES, label='Subject Type')
    class Meta:
        fields = '__all__'
        exclude = ['subject_type', 'subject_subtype']


