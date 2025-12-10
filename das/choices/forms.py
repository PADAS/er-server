import re

from django import forms
from django.forms import BaseModelFormSet

from choices.models import Choice
from core.widget import IconKeyInput, get_icon_select_list


class ChoiceForm(forms.ModelForm):
    icon = forms.CharField(required=False, widget=IconKeyInput(image_list_fn=get_icon_select_list))

    class Meta:
        model = Choice
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make value field required
        self.fields["value"].required = True

    def clean_field(self):
        """
        Validate that field contains only unicode word characters
        (letters, numbers, underscores) - no spaces.
        """
        field = self.cleaned_data.get("field")
        if field and not re.match(r"^\w+$", field):
            raise forms.ValidationError(
                "Field must contain only letters, numbers, and underscores (no spaces). " f"Got: '{field}'"
            )
        return field

    def clean_value(self):
        """
        Validate that value is required and contains only unicode word characters
        (letters, numbers, underscores) - no spaces.
        """
        value = self.cleaned_data.get("value")
        if not value:
            raise forms.ValidationError("Value is required and cannot be empty.")
        if not re.match(r"^\w+$", value):
            raise forms.ValidationError(
                "Value must contain only letters, numbers, and underscores (no spaces). " f"Got: '{value}'"
            )
        return value


class CSVImportForm(forms.Form):
    """Form for uploading CSV file to import choices"""

    csv_file = forms.FileField(
        label="CSV File",
        help_text="Upload a CSV file with columns: model, field, value, display (optional), icon, ordernum",
        widget=forms.FileInput(attrs={"accept": ".csv"}),
    )

    def clean_csv_file(self):
        """Validate that uploaded file is a CSV"""
        csv_file = self.cleaned_data.get("csv_file")

        if not csv_file:
            raise forms.ValidationError("No file uploaded")

        if not csv_file.name.endswith(".csv"):
            raise forms.ValidationError("File must be a CSV file (.csv)")

        # Check file size (limit to 10MB)
        if csv_file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File size must be under 10MB")

        return csv_file


class ChoiceFormSet(BaseModelFormSet):
    """Custom formset to ensure value field validation works with list_editable"""

    def clean(self):
        """Validate that value field is not empty and contains only unicode word characters"""
        if any(self.errors):
            return
        for form in self.forms:
            if form.cleaned_data:
                value = form.cleaned_data.get("value")
                if not value:
                    form.add_error("value", "Value is required and cannot be empty.")
                elif not re.match(r"^\w+$", value):
                    form.add_error(
                        "value",
                        "Value must contain only letters, numbers, and underscores (no spaces). " f"Got: '{value}'",
                    )
                # Also validate field format
                field = form.cleaned_data.get("field")
                if field and not re.match(r"^\w+$", field):
                    form.add_error(
                        "field",
                        "Field must contain only letters, numbers, and underscores (no spaces). " f"Got: '{field}'",
                    )
