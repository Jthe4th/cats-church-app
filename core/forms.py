from django import forms
from datetime import date

from .models import Person


class KioskVisitorForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = [
            "first_name", "middle_initial", "last_name", "street_address",
            "phone", "email", "birth_month", "birth_day",
        ]

    def clean(self):
        cleaned = super().clean()
        month, day = cleaned.get("birth_month"), cleaned.get("birth_day")
        if bool(month) != bool(day):
            raise forms.ValidationError("Enter both birth month and day, or leave both blank.")
        if month and day:
            try:
                date(2000, month, day)  # Allow February 29 without collecting a birth year.
            except ValueError:
                raise forms.ValidationError("Enter a valid birthday.")
        return cleaned


class PersonForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        include_confidential = kwargs.pop("include_confidential", False)
        super().__init__(*args, **kwargs)
        if not include_confidential and "confidential_notes" in self.fields:
            self.fields.pop("confidential_notes")
        for name, field in self.fields.items():
            widget = field.widget
            if name == "is_active":
                widget.attrs.setdefault("class", "form-check-input")
                continue
            if name in {"member_type", "family"}:
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")

    class Meta:
        model = Person
        fields = [
            "first_name",
            "middle_initial",
            "last_name",
            "street_address",
            "city",
            "state_province",
            "postal_code",
            "country",
            "phone",
            "email",
            "notes",
            "confidential_notes",
            "birth_month",
            "birth_day",
            "photo",
            "member_type",
            "family",
            "tags",
            "is_active",
        ]
        widgets = {
            "birth_month": forms.NumberInput(attrs={"min": 1, "max": 12}),
            "birth_day": forms.NumberInput(attrs={"min": 1, "max": 31}),
        }
