from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
import csv

from .fonts import ALL_FONT_CHOICES
from .models import Attendance, Family, Person, Service, SystemSetting, Tag


class PersonInline(admin.TabularInline):
    model = Person
    extra = 1
    fields = ("first_name", "middle_initial", "last_name", "member_type", "phone", "email", "is_active")


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    inlines = (PersonInline,)
    change_form_template = "admin/core/family/change_form.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        members = []
        if object_id:
            members = list(
                Person.objects.filter(family_id=object_id).order_by("last_name", "first_name")
            )
        extra_context["family_members"] = members
        return super().changeform_view(request, object_id, form_url, extra_context)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "middle_initial",
        "last_name",
        "member_type",
        "family",
        "is_active",
        "photo_preview",
    )
    list_filter = ("member_type", "is_active")
    search_fields = ("first_name", "middle_initial", "last_name", "phone", "email")
    autocomplete_fields = ("family", "tags")
    change_form_template = "admin/core/person/change_form.html"

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if request.user.is_superuser or request.user.groups.filter(name="Pastor").exists():
            return exclude
        exclude.append("confidential_notes")
        return exclude

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        confidential = form.base_fields.get("confidential_notes")
        if confidential:
            confidential.label = "Confidential notes (Pastor only)"
            confidential.help_text = 'Confidential note is only visible to users in the "pastor" group.'
            existing_class = confidential.widget.attrs.get("class", "")
            confidential.widget.attrs["class"] = f"{existing_class} confidential-notes-field".strip()
        return form

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        attendances = []
        possible_duplicates = []
        if object_id:
            attendances = list(
                Attendance.objects.filter(person_id=object_id)
                .select_related("service")
                .order_by("-service__date", "-checked_in_at")
            )
            person = Person.objects.filter(id=object_id).first()
            if person:
                possible_duplicates = (
                    Person.objects.filter(last_name__iexact=person.last_name)
                    .exclude(id=person.id)
                    .order_by("first_name", "last_name")
                )
        extra_context["attendances"] = attendances
        extra_context["possible_duplicates"] = possible_duplicates
        return super().changeform_view(request, object_id, form_url, extra_context)

    def photo_preview(self, obj):
        if not obj.photo:
            return "-"
        return format_html('<img src="{}" style="height: 32px; width: 32px; object-fit: cover; border-radius: 4px;" />', obj.photo.url)

    photo_preview.short_description = "Photo"


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("label", "date", "status")
    list_filter = ("label",)
    search_fields = ("label",)
    change_form_template = "admin/core/service/change_form.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        attendees = []
        missing_members = []
        first_time_visitors = []
        if object_id:
            if request.method == "POST" and request.POST.get("action") in {"close_service", "reopen_service"}:
                service = Service.objects.filter(id=object_id).first()
                if service:
                    if request.POST.get("action") == "close_service":
                        service.status = Service.CLOSED
                    else:
                        service.status = Service.OPEN
                    service.save(update_fields=["status"])
                return redirect(request.path)
            if request.method == "GET" and request.GET.get("live_counts") == "1":
                attended_ids = list(
                    Attendance.objects.filter(service_id=object_id).values_list("person_id", flat=True)
                )
                service = Service.objects.filter(id=object_id).first()
                first_time_count = 0
                if service and attended_ids:
                    prior_attendance_ids = Attendance.objects.filter(
                        person_id__in=attended_ids,
                        service__date__lt=service.date,
                    ).values_list("person_id", flat=True)
                    first_time_count = (
                        Person.objects.filter(id__in=attended_ids, member_type=Person.VISITOR)
                        .exclude(id__in=prior_attendance_ids)
                        .count()
                    )
                return JsonResponse(
                    {
                        "attendee_count": len(attended_ids),
                        "first_time_visitor_count": first_time_count,
                    }
                )
            if request.method == "POST" and request.POST.get("action") == "check_in_missing":
                service = Service.objects.filter(id=object_id).first()
                if service and service.status == Service.CLOSED:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return HttpResponse(status=409)
                    return redirect(request.path)
                person_id = request.POST.get("person_id")
                if person_id and person_id.isdigit():
                    Attendance.objects.get_or_create(
                        person_id=int(person_id),
                        service_id=object_id,
                    )
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return HttpResponse(status=204)
                return redirect(request.path)
            service = Service.objects.filter(id=object_id).first()
            attendees = list(
                Attendance.objects.filter(service_id=object_id)
                .select_related("person")
                .order_by("-checked_in_at", "person__last_name", "person__first_name")
            )
            attended_ids = Attendance.objects.filter(service_id=object_id).values_list("person_id", flat=True)
            missing_members = (
                Person.objects.filter(member_type=Person.MEMBER, is_active=True)
                .exclude(id__in=attended_ids)
                .order_by("last_name", "first_name")
            )
            if service:
                prior_attendance_ids = Attendance.objects.filter(
                    person_id__in=attended_ids,
                    service__date__lt=service.date,
                ).values_list("person_id", flat=True)
                first_time_visitors = (
                    Person.objects.filter(id__in=attended_ids, member_type=Person.VISITOR)
                    .exclude(id__in=prior_attendance_ids)
                    .order_by("last_name", "first_name")
                )
            export = request.GET.get("export")
            if export in {"attendees", "first_time"} and service:
                response = HttpResponse(content_type="text/csv; charset=utf-8")
                suffix = "attendees" if export == "attendees" else "first_time_visitors"
                response["Content-Disposition"] = (
                    f'attachment; filename="{suffix}_{service.date}.csv"'
                )
                response.write("\ufeff")
                writer = csv.writer(response)
                if export == "attendees":
                    writer.writerow(
                        [
                            "First Name",
                            "Middle Initial",
                            "Last Name",
                            "Check-in Time",
                            "Family",
                            "Phone",
                            "Email",
                            "Address",
                            "City",
                            "State/Province",
                            "Postal Code",
                            "Country",
                        ]
                    )
                    for attendance in attendees:
                        person = attendance.person
                        writer.writerow(
                            [
                                person.first_name,
                                person.middle_initial or "",
                                person.last_name,
                                attendance.checked_in_at.isoformat() if attendance.checked_in_at else "",
                                person.family.name if person.family else "",
                                person.phone or "",
                                person.email or "",
                                person.street_address or "",
                                person.city or "",
                                person.state_province or "",
                                person.postal_code or "",
                                person.country or "",
                            ]
                        )
                else:
                    writer.writerow(
                        [
                            "First Name",
                            "Middle Initial",
                            "Last Name",
                            "Phone",
                            "Email",
                            "Address",
                            "City",
                            "State/Province",
                            "Postal Code",
                            "Country",
                        ]
                    )
                    for person in first_time_visitors:
                        writer.writerow(
                            [
                                person.first_name,
                                person.middle_initial or "",
                                person.last_name,
                                person.phone or "",
                                person.email or "",
                                person.street_address or "",
                                person.city or "",
                                person.state_province or "",
                                person.postal_code or "",
                                person.country or "",
                            ]
                        )
                return response
        extra_context["attendees"] = attendees
        extra_context["service_status"] = (
            Service.objects.filter(id=object_id).values_list("status", flat=True).first() if object_id else Service.OPEN
        )
        extra_context["attendee_count"] = len(attendees)
        extra_context["missing_members"] = missing_members
        extra_context["missing_member_count"] = len(missing_members)
        extra_context["first_time_visitors"] = first_time_visitors
        extra_context["first_time_visitor_count"] = len(first_time_visitors)
        return super().changeform_view(request, object_id, form_url, extra_context)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("person", "service", "checked_in_at")
    list_filter = ("service",)
    search_fields = ("person__first_name", "person__last_name")
    autocomplete_fields = ("person", "service")
    actions = ("print_nametags",)

    def print_nametags(self, request: HttpRequest, queryset):
        attendance_ids = list(queryset.values_list("id", flat=True))
        if not attendance_ids:
            return None
        ids_param = ",".join(str(att_id) for att_id in attendance_ids)
        return HttpResponseRedirect(f"/print-batch/?ids={ids_param}")

    print_nametags.short_description = "Print selected nametags"

    def get_model_perms(self, request):
        # Hide from the admin app list while keeping URLs accessible.
        return {}


admin.site.unregister(Group)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value")
    search_fields = ("key", "value")
    change_form_template = "admin/core/systemsetting/change_form.html"

    YES_NO_KEYS = {"hide_last_name", "kiosk_print_mode", "kiosk_print_iframe", "enable_google_fonts"}
    SOURCE_KEYS = {"welcome_heading_font_source", "label_font_source"}
    FONT_KEYS = {"label_font", "welcome_heading_font"}

    class Form(forms.ModelForm):
        FONT_CHOICES = ALL_FONT_CHOICES
        SOURCE_CHOICES = [("system", "System"), ("google", "Google")]

        class Meta:
            model = SystemSetting
            fields = "__all__"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance and self.instance.key in SystemSettingAdmin.FONT_KEYS:
                self.fields["value"] = forms.ChoiceField(choices=self.FONT_CHOICES)
                self.fields["value"].widget.choices = self.FONT_CHOICES
            if self.instance and self.instance.key in SystemSettingAdmin.YES_NO_KEYS:
                self.fields["value"] = forms.ChoiceField(choices=[("No", "No"), ("Yes", "Yes")])
            if self.instance and self.instance.key in SystemSettingAdmin.SOURCE_KEYS:
                self.fields["value"] = forms.ChoiceField(choices=self.SOURCE_CHOICES)
            if self.instance and self.instance.key in {"kiosk_background_color", "kiosk_background_color_darkmode"}:
                self.fields["value"] = forms.RegexField(
                    regex=r"^#[0-9a-fA-F]{6}$",
                    widget=forms.TextInput(attrs={"placeholder": "#ffffff"}),
                    help_text='Hex color value, e.g. "#ffffff".',
                    error_messages={"invalid": "Enter a valid hex color in the format #RRGGBB."},
                )

    form = Form

    COLOR_KEYS = {
        "first_name_color",
        "last_name_color",
        "kiosk_background_color",
        "kiosk_background_color_darkmode",
    }

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "bulk/",
                self.admin_site.admin_view(self.bulk_edit_view),
                name="core_systemsetting_bulk",
            )
        ]
        return custom_urls + urls

    def bulk_edit_view(self, request):
        settings_qs = list(SystemSetting.objects.order_by("key"))
        field_to_setting = {f"setting_{item.id}": item for item in settings_qs}

        class BulkSettingsForm(forms.Form):
            pass

        for field_name, setting_obj in field_to_setting.items():
            initial_value = setting_obj.value or ""
            if setting_obj.key in self.COLOR_KEYS:
                field = forms.RegexField(
                    regex=r"^#[0-9a-fA-F]{6}$",
                    initial=initial_value or "#ffffff",
                    widget=forms.TextInput(attrs={"placeholder": "#ffffff", "class": "vTextField"}),
                    help_text='Hex color value, e.g. "#ffffff".',
                    error_messages={"invalid": "Enter a valid hex color in the format #RRGGBB."},
                    required=False,
                    label=setting_obj.key,
                )
            elif setting_obj.key in self.YES_NO_KEYS:
                field = forms.ChoiceField(
                    choices=[("No", "No"), ("Yes", "Yes")],
                    initial=initial_value or "No",
                    required=False,
                    label=setting_obj.key,
                    widget=forms.Select(attrs={"class": "vSelect"}),
                )
            elif setting_obj.key in self.SOURCE_KEYS:
                field = forms.ChoiceField(
                    choices=[("system", "System"), ("google", "Google")],
                    initial=initial_value or "system",
                    required=False,
                    label=setting_obj.key,
                    widget=forms.Select(attrs={"class": "vSelect"}),
                )
            elif setting_obj.key in self.FONT_KEYS:
                field = forms.ChoiceField(
                    choices=ALL_FONT_CHOICES,
                    initial=initial_value or "Arial",
                    required=False,
                    label=setting_obj.key,
                    widget=forms.Select(attrs={"class": "vSelect"}),
                )
            else:
                field = forms.CharField(
                    initial=initial_value,
                    required=False,
                    label=setting_obj.key,
                    widget=forms.TextInput(attrs={"class": "vTextField"}),
                )
            BulkSettingsForm.base_fields[field_name] = field

        if request.method == "POST":
            form = BulkSettingsForm(request.POST)
            if form.is_valid():
                for field_name, setting_obj in field_to_setting.items():
                    setting_obj.value = form.cleaned_data.get(field_name, "")
                    setting_obj.save(update_fields=["value"])
                self.message_user(request, "System settings updated.")
                return redirect("admin:core_systemsetting_bulk")
        else:
            form = BulkSettingsForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "System settings",
            "form": form,
            "rows": [(form[field_name], setting_obj) for field_name, setting_obj in field_to_setting.items()],
            "has_view_permission": True,
            "has_change_permission": True,
        }
        return TemplateResponse(request, "admin/core/systemsetting/bulk_edit.html", context)

    def get_model_perms(self, request):
        # Hide regular per-row editor from admin app list; use bulk settings page instead.
        return {}
