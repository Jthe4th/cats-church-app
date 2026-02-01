from django import forms

from .models import Person


class PersonForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
