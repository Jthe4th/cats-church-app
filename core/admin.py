from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import Group
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from jazzmin.settings import THEMES
import csv

from .audit import log_event
from .fonts import ALL_FONT_CHOICES
from .models import Attendance, AuditLog, Family, Person, Service, SystemSetting, Tag
from .permissions import can_manage_configuration, can_view_confidential_notes
from .settings_store import get_setting


class PersonInline(admin.StackedInline):
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
        if can_view_confidential_notes(request.user):
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
    save_on_top = False

    def has_delete_permission(self, request, obj=None):
        # Keep services immutable from this workflow to avoid accidental data loss.
        return False

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["show_delete"] = False
        context["show_delete_link"] = False
        context["show_save_and_add_another"] = False
        context["show_save_and_continue"] = False
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

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
                        action = AuditLog.ACTION_SERVICE_CLOSE
                        message = "Service closed from Manage Church Service."
                    else:
                        service.status = Service.OPEN
                        action = AuditLog.ACTION_SERVICE_REOPEN
                        message = "Service reopened from Manage Church Service."
                    service.save(update_fields=["status"])
                    log_event(action, user=request.user, service=service, message=message)
                return redirect(request.path)
            if request.method == "GET" and request.GET.get("live_counts") == "1":
                attendees_qs = (
                    Attendance.objects.filter(service_id=object_id)
                    .select_related("person")
                    .order_by("person__last_name", "person__first_name", "-checked_in_at")
                )
                attended_ids = list(attendees_qs.values_list("person_id", flat=True))
                service = Service.objects.filter(id=object_id).first()
                first_time_count = 0
                first_time_visitors = []
                if service and attended_ids:
                    prior_attendance_ids = Attendance.objects.filter(
                        person_id__in=attended_ids,
                        service__date__lt=service.date,
                    ).values_list("person_id", flat=True)
                    first_time_qs = (
                        Person.objects.filter(id__in=attended_ids, member_type=Person.VISITOR)
                        .exclude(id__in=prior_attendance_ids)
                        .only("id", "first_name", "middle_initial", "last_name")
                        .order_by("last_name", "first_name")
                    )
                    first_time_count = first_time_qs.count()
                    for person in first_time_qs:
                        middle = f" {person.middle_initial}." if person.middle_initial else ""
                        first_time_visitors.append(
                            {
                                "person_id": person.id,
                                "name": f"{person.first_name}{middle} {person.last_name}",
                            }
                        )
                missing_count = (
                    Person.objects.filter(member_type=Person.MEMBER, is_active=True)
                    .exclude(id__in=attended_ids)
                    .count()
                )
                attendees = []
                for attendance in attendees_qs:
                    person = attendance.person
                    middle = f" {person.middle_initial}." if person.middle_initial else ""
                    attendees.append(
                        {
                            "attendance_id": attendance.id,
                            "person_id": person.id,
                            "name": f"{person.first_name}{middle} {person.last_name}",
                            "checked_in_at": timezone.localtime(attendance.checked_in_at).strftime("%b %d, %Y %I:%M %p"),
                        }
                    )
                return JsonResponse(
                    {
                        "service_id": int(object_id),
                        "service_label": service.label if service else "",
                        "service_status": service.status if service else Service.OPEN,
                        "attendee_count": len(attended_ids),
                        "first_time_visitor_count": first_time_count,
                        "first_time_visitors": first_time_visitors,
                        "missing_member_count": missing_count,
                        "attendees": attendees,
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
                    attendance, created = Attendance.objects.get_or_create(
                        person_id=int(person_id),
                        service_id=object_id,
                    )
                    if created:
                        log_event(
                            AuditLog.ACTION_CHECKIN,
                            user=request.user,
                            service=service,
                            person=attendance.person,
                            attendance=attendance,
                            message="Checked in from missing-members quick action.",
                            metadata={"source": "admin_service_missing"},
                        )
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return HttpResponse(status=204)
                return redirect(request.path)
            if request.method == "POST" and request.POST.get("action") == "undo_checkin":
                service = Service.objects.filter(id=object_id).first()
                if service and service.status == Service.CLOSED:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return HttpResponse(status=409)
                    return redirect(request.path)
                attendance_id = request.POST.get("attendance_id")
                if attendance_id and attendance_id.isdigit():
                    attendance = (
                        Attendance.objects.filter(id=int(attendance_id), service_id=object_id)
                        .select_related("person", "service")
                        .first()
                    )
                    if attendance:
                        log_event(
                            AuditLog.ACTION_UNDO_CHECKIN,
                            user=request.user,
                            service=attendance.service,
                            person=attendance.person,
                            attendance=attendance,
                            message="Attendance removed from Manage Church Service.",
                            metadata={"source": "admin_service_attendees"},
                        )
                        attendance.delete()
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
        extra_context["admin_auto_print"] = get_setting("kiosk_print_mode", "No").strip().lower() in {"yes", "true", "1"}
        extra_context["admin_iframe_print"] = get_setting("kiosk_print_iframe", "No").strip().lower() in {"yes", "true", "1"}
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
    ADMIN_SKIN_KEYS = {"admin_skin"}
    LOGO_UPLOAD_KEYS = {"kiosk_logo_path"}
    PX_INT_KEYS = {"kiosk_logo_width_px", "kiosk_logo_height_px"}
    PERCENT_INT_KEYS = {"label_first_name_scale", "label_last_name_scale"}
    ADMIN_SKIN_CHOICES = [(name, name.replace("_", " ").title()) for name in THEMES.keys()]

    @staticmethod
    def _save_logo_file(uploaded: UploadedFile) -> str:
        saved_path = default_storage.save(f"branding/{uploaded.name}", uploaded)
        normalized = saved_path.replace("\\", "/")
        return f"{settings.MEDIA_URL.rstrip('/')}/{normalized}"

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
            if self.instance and self.instance.key in SystemSettingAdmin.ADMIN_SKIN_KEYS:
                self.fields["value"] = forms.ChoiceField(choices=SystemSettingAdmin.ADMIN_SKIN_CHOICES)
            if self.instance and self.instance.key in SystemSettingAdmin.YES_NO_KEYS:
                self.fields["value"] = forms.ChoiceField(choices=[("No", "No"), ("Yes", "Yes")])
            if self.instance and self.instance.key in SystemSettingAdmin.SOURCE_KEYS:
                self.fields["value"] = forms.ChoiceField(choices=self.SOURCE_CHOICES)
            if self.instance and self.instance.key in SystemSettingAdmin.LOGO_UPLOAD_KEYS:
                self.fields["value"] = forms.FileField(
                    required=False,
                    widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
                    help_text=f'Upload logo image (PNG/JPG/SVG/WebP). Current: "{self.instance.value or "(none)"}".',
                )
            if self.instance and self.instance.key in SystemSettingAdmin.PX_INT_KEYS:
                self.fields["value"] = forms.IntegerField(
                    required=False,
                    min_value=0,
                    widget=forms.NumberInput(attrs={"placeholder": "Auto"}),
                    help_text='Pixel value, e.g. "200". Leave blank (or 0) for auto.',
                )
            if self.instance and self.instance.key in SystemSettingAdmin.PERCENT_INT_KEYS:
                self.fields["value"] = forms.IntegerField(
                    required=False,
                    min_value=50,
                    max_value=200,
                    widget=forms.NumberInput(attrs={"placeholder": "100"}),
                    help_text='Percent scale from 50 to 200. "100" keeps default size.',
                )
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
    FRIENDLY_LABELS = {
        "enable_google_fonts": "Enable Google Fonts",
        "first_name_color": "First Name Color",
        "hide_last_name": "Hide Last Name",
        "kiosk_background_color": "Kiosk Background Color (Light)",
        "kiosk_background_color_darkmode": "Kiosk Background Color (Dark)",
        "kiosk_logo_path": "Kiosk Logo Image",
        "kiosk_logo_width_px": "Kiosk Logo Width (px)",
        "kiosk_logo_height_px": "Kiosk Logo Height (px)",
        "kiosk_print_mode": "Auto Print Mode",
        "kiosk_print_iframe": "In-Page Print Preview Mode",
        "admin_skin": "Admin Skin",
        "label_font": "Label Font",
        "label_font_source": "Label Font Source",
        "label_first_name_scale": "Label First Name Size (%)",
        "label_last_name_scale": "Label Last Name Size (%)",
        "last_name_color": "Last Name Color",
        "welcome_heading": "Welcome Heading Text",
        "welcome_heading_font": "Welcome Heading Font",
        "welcome_heading_font_source": "Welcome Heading Font Source",
    }
    SECTION_ORDER = [
        "Kiosk Preferences",
        "Admin Appearance",
        "Label & Printing",
        "Font Platform",
        "Other",
    ]
    SECTION_KEYS = {
        "Kiosk Preferences": {
            "welcome_heading",
            "welcome_heading_font",
            "welcome_heading_font_source",
            "kiosk_background_color",
            "kiosk_background_color_darkmode",
            "kiosk_logo_path",
            "kiosk_logo_width_px",
            "kiosk_logo_height_px",
        },
        "Label & Printing": {
            "first_name_color",
            "last_name_color",
            "hide_last_name",
            "label_font",
            "label_font_source",
            "label_first_name_scale",
            "label_last_name_scale",
            "kiosk_print_mode",
            "kiosk_print_iframe",
        },
        "Admin Appearance": {"admin_skin"},
        "Font Platform": {"enable_google_fonts"},
    }

    @classmethod
    def _section_for_key(cls, key: str) -> str:
        for section, keys in cls.SECTION_KEYS.items():
            if key in keys:
                return section
        return "Other"

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
        if not can_manage_configuration(request.user):
            return redirect("/admin/")
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
            elif setting_obj.key in self.ADMIN_SKIN_KEYS:
                field = forms.ChoiceField(
                    choices=self.ADMIN_SKIN_CHOICES,
                    initial=initial_value or "default",
                    required=False,
                    label=setting_obj.key,
                    widget=forms.Select(attrs={"class": "vSelect"}),
                )
            elif setting_obj.key in self.LOGO_UPLOAD_KEYS:
                field = forms.FileField(
                    required=False,
                    label=setting_obj.key,
                    widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
                    help_text=f'Upload logo image (PNG/JPG/SVG/WebP). Current: "{initial_value or "(none)"}".',
                )
            elif setting_obj.key in self.PX_INT_KEYS:
                cleaned_initial = initial_value if str(initial_value).isdigit() else ""
                field = forms.IntegerField(
                    initial=cleaned_initial,
                    required=False,
                    min_value=0,
                    label=setting_obj.key,
                    widget=forms.NumberInput(attrs={"class": "vTextField", "placeholder": "Auto"}),
                    help_text='Pixel value, e.g. "200". Leave blank (or 0) for auto.',
                )
            elif setting_obj.key in self.PERCENT_INT_KEYS:
                cleaned_initial = initial_value if str(initial_value).isdigit() else "100"
                field = forms.IntegerField(
                    initial=cleaned_initial,
                    required=False,
                    min_value=50,
                    max_value=200,
                    label=setting_obj.key,
                    widget=forms.NumberInput(attrs={"class": "vTextField", "placeholder": "100"}),
                    help_text='Percent scale from 50 to 200. "100" keeps default size.',
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
                    raw_value = form.cleaned_data.get(field_name, "")
                    old_value = setting_obj.value or ""
                    if setting_obj.key in self.LOGO_UPLOAD_KEYS:
                        if isinstance(raw_value, UploadedFile):
                            new_value = self._save_logo_file(raw_value)
                        else:
                            new_value = old_value
                    else:
                        new_value = "" if raw_value in (None, 0) else str(raw_value)
                    if str(old_value) == str(new_value):
                        continue
                    setting_obj.value = new_value
                    setting_obj.save(update_fields=["value"])
                    log_event(
                        AuditLog.ACTION_SETTING_CHANGE,
                        user=request.user,
                        message=f'Setting "{setting_obj.key}" updated.',
                        metadata={"key": setting_obj.key, "old_value": old_value, "new_value": new_value},
                    )
                self.message_user(request, "System settings updated.")
                return redirect("admin:core_systemsetting_bulk")
        else:
            form = BulkSettingsForm()

        section_map = {name: [] for name in self.SECTION_ORDER}
        for field_name, setting_obj in field_to_setting.items():
            section = self._section_for_key(setting_obj.key)
            section_map.setdefault(section, []).append(
                (
                    form[field_name],
                    setting_obj,
                    self.FRIENDLY_LABELS.get(setting_obj.key, setting_obj.key.replace("_", " ").title()),
                )
            )
        sections = [
            {"name": section_name, "rows": section_map.get(section_name, [])}
            for section_name in self.SECTION_ORDER
            if section_map.get(section_name)
        ]

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "System settings",
            "form": form,
            "sections": sections,
            "has_view_permission": True,
            "has_change_permission": True,
        }
        return TemplateResponse(request, "admin/core/systemsetting/bulk_edit.html", context)

    def get_model_perms(self, request):
        # Hide regular per-row editor from admin app list; use bulk settings page instead.
        return {}

    def has_module_permission(self, request):
        return can_manage_configuration(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_configuration(request.user)

    def has_change_permission(self, request, obj=None):
        return can_manage_configuration(request.user)

    def save_model(self, request, obj, form, change):
        old_value = ""
        if change:
            old_value = SystemSetting.objects.filter(pk=obj.pk).values_list("value", flat=True).first() or ""
        if obj.key in self.LOGO_UPLOAD_KEYS:
            raw_value = form.cleaned_data.get("value")
            if isinstance(raw_value, UploadedFile):
                obj.value = self._save_logo_file(raw_value)
            elif change:
                obj.value = old_value
            else:
                obj.value = obj.value or ""
        super().save_model(request, obj, form, change)
        new_value = obj.value or ""
        if not change or str(old_value) != str(new_value):
            log_event(
                AuditLog.ACTION_SETTING_CHANGE,
                user=request.user,
                message=f'Setting "{obj.key}" updated.',
                metadata={"key": obj.key, "old_value": old_value, "new_value": new_value},
            )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "service", "person", "message")
    list_filter = ("action", "created_at")
    search_fields = ("message", "actor__username", "person__first_name", "person__last_name", "service__label")
    readonly_fields = ("created_at", "action", "actor", "service", "person", "attendance", "message", "metadata")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_model_perms(self, request):
        # Keep access via the custom report entry in the admin index.
        return {}
