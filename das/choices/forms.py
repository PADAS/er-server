from django import forms

from choices.models import Choice
from core.widget import IconKeyInput, get_icon_select_list


class ChoiceForm(forms.ModelForm):
    icon = forms.CharField(required=False, widget=IconKeyInput(image_list_fn=get_icon_select_list))

    class Meta:
        model = Choice
        fields = "__all__"


class CSVImportForm(forms.Form):
    """Form for uploading CSV file to import choices"""

    csv_file = forms.FileField(
        label="CSV File",
        help_text="Upload a CSV file with columns: model, field, value, display, icon, ordernum",
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
