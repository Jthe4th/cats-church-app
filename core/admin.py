from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import Group
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q
from jazzmin.settings import THEMES
import csv
import json

from .audit import log_event
from .fonts import ALL_FONT_CHOICES, SYSTEM_FONT_CHOICES
from .member_queries import members_active_for_service
from .models import Attendance, AuditLog, Family, Person, Service, SystemSetting, Tag
from .permissions import can_manage_configuration, can_view_confidential_notes
from .printnode import PRINT_MODE_CONNECTED, PRINT_MODE_PRINTNODE, PRINT_MODE_SERVER, verify_printnode_api_key
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
    ordering = ("-date", "-id")
    sortable_by = ()
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
                        .only("id", "first_name", "middle_initial", "last_name", "photo")
                        .order_by("last_name", "first_name")
                    )
                    first_time_count = first_time_qs.count()
                    for person in first_time_qs:
                        middle = f" {person.middle_initial}." if person.middle_initial else ""
                        first_time_visitors.append(
                            {
                                "person_id": person.id,
                                "name": f"{person.first_name}{middle} {person.last_name}",
                                "initials": person.initials,
                                "photo_url": person.photo.url if person.photo else "",
                            }
                        )
                missing_count = (
                    members_active_for_service(service)
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
                            "initials": person.initials,
                            "photo_url": person.photo.url if person.photo else "",
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
            if request.method == "GET" and request.GET.get("manual_search") is not None:
                query = request.GET.get("manual_search", "").strip()
                if len(query) < 2:
                    return JsonResponse({"results": []})
                people_qs = (
                    Person.objects.filter(
                        Q(first_name__icontains=query)
                        | Q(last_name__icontains=query)
                        | Q(phone__icontains=query)
                        | Q(email__icontains=query)
                    )
                    .select_related("family")
                    .order_by("last_name", "first_name")[:20]
                )
                person_ids = list(people_qs.values_list("id", flat=True))
                checked_in_ids = set(
                    Attendance.objects.filter(service_id=object_id, person_id__in=person_ids).values_list("person_id", flat=True)
                )
                results = []
                for person in people_qs:
                    middle = f" {person.middle_initial}." if person.middle_initial else ""
                    results.append(
                        {
                            "id": person.id,
                            "name": f"{person.first_name}{middle} {person.last_name}",
                            "family": person.family.name if person.family else "",
                            "phone": person.phone or "",
                            "initials": person.initials,
                            "photo_url": person.photo.url if person.photo else "",
                            "checked_in": person.id in checked_in_ids,
                        }
                    )
                return JsonResponse({"results": results})
            if request.method == "POST" and request.POST.get("action") in {"manual_checkin_person", "manual_print_person"}:
                service = Service.objects.filter(id=object_id).first()
                if service and service.status == Service.CLOSED:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return HttpResponse(status=409)
                    return redirect(request.path)
                person_id = request.POST.get("person_id")
                if person_id and person_id.isdigit():
                    person = Person.objects.filter(id=int(person_id)).first()
                    if person:
                        attendance, created = Attendance.objects.get_or_create(
                            person_id=person.id,
                            service_id=object_id,
                        )
                        if created:
                            log_event(
                                AuditLog.ACTION_CHECKIN,
                                user=request.user,
                                service=service,
                                person=person,
                                attendance=attendance,
                                message="Manual check-in from Manage Church Service.",
                                metadata={"source": "manual_attendance"},
                            )
                        if request.POST.get("action") == "manual_print_person":
                            auto_print = get_setting("kiosk_print_mode", "No").strip().lower() in {"yes", "true", "1"}
                            print_url = f"/print/{attendance.id}/"
                            if auto_print:
                                print_url = f"{print_url}?auto=1"
                            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                                return JsonResponse({"print_url": print_url})
                            return redirect(print_url)
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return HttpResponse(status=204)
                return redirect(request.path)
            if request.method == "POST" and request.POST.get("action") in {"manual_create_visitor", "manual_create_visitor_print"}:
                service = Service.objects.filter(id=object_id).first()
                if service and service.status == Service.CLOSED:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return HttpResponse(status=409)
                    return redirect(request.path)
                first_name = request.POST.get("first_name", "").strip()
                last_name = request.POST.get("last_name", "").strip()
                middle_initial = request.POST.get("middle_initial", "").strip()[:1]
                phone = request.POST.get("phone", "").strip()
                email = request.POST.get("email", "").strip()
                if not first_name or not last_name:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({"error": "First and last name are required."}, status=400)
                    return redirect(request.path)
                person = Person.objects.create(
                    first_name=first_name,
                    middle_initial=middle_initial,
                    last_name=last_name,
                    phone=phone,
                    email=email,
                    member_type=Person.VISITOR,
                )
                attendance, created = Attendance.objects.get_or_create(
                    person_id=person.id,
                    service_id=object_id,
                )
                if created:
                    log_event(
                        AuditLog.ACTION_CHECKIN,
                        user=request.user,
                        service=service,
                        person=person,
                        attendance=attendance,
                        message="Manual new visitor check-in from Manage Church Service.",
                        metadata={"source": "manual_attendance_new"},
                    )
                if request.POST.get("action") == "manual_create_visitor_print":
                    auto_print = get_setting("kiosk_print_mode", "No").strip().lower() in {"yes", "true", "1"}
                    print_url = f"/print/{attendance.id}/"
                    if auto_print:
                        print_url = f"{print_url}?auto=1"
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({"print_url": print_url})
                    return redirect(print_url)
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({"created_person_id": person.id, "checked_in": True})
                return redirect(request.path)
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
                members_active_for_service(service)
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
    SOURCE_KEYS = {"welcome_heading_font_source"}
    FONT_KEYS = {"label_font", "welcome_heading_font"}
    ADMIN_SKIN_KEYS = {"admin_skin"}
    PRINT_MODE_KEYS = {"print_mode"}
    BROTHER_MEDIA_KEYS = {"brother_label_media"}
    JSON_KEYS = {"printnode_printer_map", "server_printer_map", "printer_profiles", "kiosk_printer_profile_map"}
    PRINTNODE_PRINTER_MAP_KEYS = {"printnode_printer_map"}
    SERVER_PRINTER_MAP_KEYS = {"server_printer_map"}
    PRINTER_PROFILE_KEYS = {"printer_profiles"}
    KIOSK_PRINTER_PROFILE_MAP_KEYS = {"kiosk_printer_profile_map"}
    SECRET_KEYS = {"printnode_api_key"}
    LOGO_UPLOAD_KEYS = {"kiosk_logo_path"}
    PX_INT_KEYS = {"kiosk_logo_width_px", "kiosk_logo_height_px"}
    PERCENT_INT_KEYS = {"label_first_name_scale", "label_last_name_scale"}
    DECIMAL_KEYS = {"printnode_label_width_in", "printnode_label_height_in", "printnode_label_margin_in"}
    INT_KEYS = {"server_printer_timeout_seconds"}
    ADMIN_SKIN_CHOICES = [(name, name.replace("_", " ").title()) for name in THEMES.keys()]
    PRINT_MODE_CHOICES = [
        (PRINT_MODE_CONNECTED, PRINT_MODE_CONNECTED),
        (PRINT_MODE_PRINTNODE, PRINT_MODE_PRINTNODE),
        (PRINT_MODE_SERVER, PRINT_MODE_SERVER),
    ]
    BROTHER_MEDIA_CHOICES = [
        ("62red", "62mm black/red/white"),
        ("62", "62mm black/white"),
    ]
    ADMIN_SKIN_PREVIEW_URL = "https://django-jazzmin.readthedocs.io/ui_customisation/"

    @staticmethod
    def _save_logo_file(uploaded: UploadedFile) -> str:
        saved_path = default_storage.save(f"branding/{uploaded.name}", uploaded)
        normalized = saved_path.replace("\\", "/")
        return f"{settings.MEDIA_URL.rstrip('/')}/{normalized}"

    @classmethod
    def _audit_value(cls, setting_obj, value):
        if setting_obj.key in cls.SECRET_KEYS and value:
            return "********"
        return value

    @staticmethod
    def _clean_printer_map(value):
        value = value or {}
        if not isinstance(value, dict):
            raise forms.ValidationError("Enter a JSON object mapping kiosk ids to PrintNode printer ids.")
        cleaned = {}
        for kiosk_id, printer_id in value.items():
            kiosk_id = str(kiosk_id).strip()
            printer_id = str(printer_id).strip()
            if not kiosk_id:
                raise forms.ValidationError("Kiosk ids cannot be blank.")
            if not printer_id.isdigit():
                raise forms.ValidationError(f'Printer id for "{kiosk_id}" must be a number.')
            cleaned[kiosk_id] = printer_id
        return cleaned

    @staticmethod
    def _clean_server_printer_map(value):
        value = value or {}
        if not isinstance(value, dict):
            raise forms.ValidationError("Enter a JSON object mapping kiosk ids to server printer addresses.")
        cleaned = {}
        for kiosk_id, printer_config in value.items():
            kiosk_id = str(kiosk_id).strip()
            if not kiosk_id:
                raise forms.ValidationError("Kiosk ids cannot be blank.")
            if isinstance(printer_config, dict):
                queue_name = str(printer_config.get("queue", "")).strip()
                if queue_name:
                    cleaned[kiosk_id] = {"queue": queue_name}
                    continue
                host = str(printer_config.get("host", "")).strip()
                port = str(printer_config.get("port", "9100")).strip()
                if not host:
                    raise forms.ValidationError(f'Printer host for "{kiosk_id}" cannot be blank.')
                if not port.isdigit():
                    raise forms.ValidationError(f'Printer port for "{kiosk_id}" must be a number.')
                port_number = int(port)
                if port_number < 1 or port_number > 65535:
                    raise forms.ValidationError(f'Printer port for "{kiosk_id}" must be between 1 and 65535.')
                cleaned[kiosk_id] = {"host": host, "port": port_number}
                continue
            raw_value = str(printer_config or "").strip()
            if not raw_value:
                raise forms.ValidationError(f'Printer address for "{kiosk_id}" cannot be blank.')
            if raw_value.startswith("queue:"):
                if not raw_value.removeprefix("queue:").strip():
                    raise forms.ValidationError(f'Printer queue for "{kiosk_id}" cannot be blank.')
            elif ":" in raw_value:
                host, port = raw_value.rsplit(":", 1)
                if not host.strip() or not port.strip().isdigit():
                    raise forms.ValidationError(f'Printer address for "{kiosk_id}" must look like 192.168.1.50:9100.')
                port_number = int(port.strip())
                if port_number < 1 or port_number > 65535:
                    raise forms.ValidationError(f'Printer port for "{kiosk_id}" must be between 1 and 65535.')
            cleaned[kiosk_id] = raw_value
        return cleaned

    @staticmethod
    def _clean_kiosk_printer_profile_map(value):
        value = value or {}
        if not isinstance(value, dict):
            raise forms.ValidationError("Enter a JSON object mapping kiosk ids to printer profile names.")
        cleaned = {}
        for kiosk_id, profile_name in value.items():
            kiosk_id = str(kiosk_id).strip()
            profile_name = str(profile_name).strip()
            if not kiosk_id:
                raise forms.ValidationError("Kiosk ids cannot be blank.")
            if not profile_name:
                raise forms.ValidationError(f'Printer profile name for "{kiosk_id}" cannot be blank.')
            cleaned[kiosk_id] = profile_name
        return cleaned

    @staticmethod
    def _clean_printer_profiles(value):
        value = value or {}
        if not isinstance(value, dict):
            raise forms.ValidationError("Enter a JSON object of printer profile definitions.")
        cleaned = {}
        for profile_name, profile in value.items():
            profile_name = str(profile_name).strip()
            if not profile_name:
                raise forms.ValidationError("Printer profile names cannot be blank.")
            if not isinstance(profile, dict):
                raise forms.ValidationError(f'Printer profile "{profile_name}" must be a JSON object.')
            backend = str(profile.get("backend", "")).strip().lower()
            if backend not in {"printnode", "server"}:
                raise forms.ValidationError(f'Printer profile "{profile_name}" must use backend "printnode" or "server".')
            cleaned_profile = {**profile, "backend": backend}
            if backend == "printnode":
                printer_id = str(profile.get("printer_id") or profile.get("printnode_printer_id") or "").strip()
                if not printer_id.isdigit():
                    raise forms.ValidationError(f'PrintNode profile "{profile_name}" must include a numeric printer_id.')
                cleaned_profile["printer_id"] = printer_id
                cleaned_profile.pop("printnode_printer_id", None)
            if backend == "server":
                target = profile.get("target")
                if not target:
                    if profile.get("queue"):
                        target = {"queue": str(profile.get("queue")).strip()}
                    elif profile.get("host"):
                        target = {"host": str(profile.get("host")).strip(), "port": profile.get("port", 9100)}
                SystemSettingAdmin._clean_server_printer_map({"profile": target})
                cleaned_profile["target"] = target
            for key in ("label_width_in", "label_height_in", "label_margin_in"):
                if key in cleaned_profile and str(cleaned_profile.get(key)).strip():
                    try:
                        value_float = float(str(cleaned_profile[key]).strip())
                    except ValueError as exc:
                        raise forms.ValidationError(f'Printer profile "{profile_name}" has an invalid {key}.') from exc
                    if value_float <= 0 or value_float > 10:
                        raise forms.ValidationError(f'Printer profile "{profile_name}" has an out-of-range {key}.')
                    cleaned_profile[key] = str(cleaned_profile[key]).strip()
            media = str(cleaned_profile.get("brother_label_media", "")).strip()
            if media:
                if media not in {"62", "62red"}:
                    raise forms.ValidationError(f'Printer profile "{profile_name}" has an invalid brother_label_media.')
                cleaned_profile["brother_label_media"] = media
            cleaned[profile_name] = cleaned_profile
        return cleaned

    class Form(forms.ModelForm):
        FONT_CHOICES = ALL_FONT_CHOICES
        LABEL_FONT_CHOICES = SYSTEM_FONT_CHOICES
        SOURCE_CHOICES = [("system", "System"), ("google", "Google")]

        class Meta:
            model = SystemSetting
            fields = "__all__"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance and self.instance.key in SystemSettingAdmin.FONT_KEYS:
                choices = self.LABEL_FONT_CHOICES if self.instance.key == "label_font" else self.FONT_CHOICES
                self.fields["value"] = forms.ChoiceField(choices=choices)
                self.fields["value"].widget.choices = choices
            if self.instance and self.instance.key in SystemSettingAdmin.ADMIN_SKIN_KEYS:
                self.fields["value"] = forms.ChoiceField(
                    choices=SystemSettingAdmin.ADMIN_SKIN_CHOICES,
                    help_text=format_html(
                        'Preview available skins in the <a href="{}" target="_blank" rel="noopener noreferrer">Jazzmin UI docs</a>.',
                        SystemSettingAdmin.ADMIN_SKIN_PREVIEW_URL,
                    ),
                )
            if self.instance and self.instance.key in SystemSettingAdmin.PRINT_MODE_KEYS:
                self.fields["value"] = forms.ChoiceField(choices=SystemSettingAdmin.PRINT_MODE_CHOICES)
            if self.instance and self.instance.key in SystemSettingAdmin.BROTHER_MEDIA_KEYS:
                self.fields["value"] = forms.ChoiceField(choices=SystemSettingAdmin.BROTHER_MEDIA_CHOICES)
            if self.instance and self.instance.key in SystemSettingAdmin.SECRET_KEYS:
                self.fields["value"] = forms.CharField(
                    required=False,
                    widget=forms.PasswordInput(render_value=True),
                    help_text="Stored locally in the database. Leave blank to disable PrintNode printing.",
                )
            if self.instance and self.instance.key in SystemSettingAdmin.JSON_KEYS:
                try:
                    initial_json = json.loads(self.instance.value or "{}")
                except json.JSONDecodeError:
                    initial_json = self.instance.value or "{}"
                help_text = 'Example: {"kiosk1": "123456", "kiosk2": "123457"}'
                if self.instance.key in SystemSettingAdmin.SERVER_PRINTER_MAP_KEYS:
                    help_text = 'Examples: {"kiosk1": "queue:Brother_QL_820NWB"} or {"kiosk1": "192.168.1.50:9100"}. Queue mode uses the server computer print queue.'
                if self.instance.key in SystemSettingAdmin.PRINTER_PROFILE_KEYS:
                    help_text = 'Example: {"front-desk-brother": {"backend": "server", "target": "queue:Brother_QL_820NWB", "label_width_in": "2.440", "label_height_in": "1.1", "brother_label_media": "62red"}}'
                if self.instance.key in SystemSettingAdmin.KIOSK_PRINTER_PROFILE_MAP_KEYS:
                    help_text = 'Example: {"kiosk1": "front-desk-brother", "kiosk2": "side-door-zebra"}. Existing direct printer maps are still used when a kiosk has no profile.'
                self.fields["value"] = forms.JSONField(
                    required=False,
                    initial=initial_json,
                    widget=forms.Textarea(attrs={"rows": 6, "cols": 70}),
                    help_text=help_text,
                )
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
            if self.instance and self.instance.key in SystemSettingAdmin.DECIMAL_KEYS:
                self.fields["value"] = forms.DecimalField(
                    required=False,
                    min_value=0,
                    max_value=10,
                    decimal_places=3,
                    max_digits=5,
                    widget=forms.NumberInput(attrs={"step": "0.001", "placeholder": "1.102"}),
                    help_text="Measurement in inches.",
                )
            if self.instance and self.instance.key in SystemSettingAdmin.INT_KEYS:
                self.fields["value"] = forms.IntegerField(
                    required=False,
                    min_value=1,
                    max_value=60,
                    widget=forms.NumberInput(attrs={"placeholder": "10"}),
                    help_text="Whole seconds from 1 to 60.",
                )
            if self.instance and self.instance.key in {"kiosk_background_color", "kiosk_background_color_darkmode"}:
                self.fields["value"] = forms.RegexField(
                    regex=r"^#[0-9a-fA-F]{6}$",
                    widget=forms.TextInput(attrs={"placeholder": "#ffffff"}),
                    help_text='Hex color value, e.g. "#ffffff".',
                    error_messages={"invalid": "Enter a valid hex color in the format #RRGGBB."},
                )

        def clean_value(self):
            value = self.cleaned_data.get("value")
            if self.instance and self.instance.key in SystemSettingAdmin.PRINTNODE_PRINTER_MAP_KEYS:
                return SystemSettingAdmin._clean_printer_map(value)
            if self.instance and self.instance.key in SystemSettingAdmin.SERVER_PRINTER_MAP_KEYS:
                return SystemSettingAdmin._clean_server_printer_map(value)
            if self.instance and self.instance.key in SystemSettingAdmin.PRINTER_PROFILE_KEYS:
                return SystemSettingAdmin._clean_printer_profiles(value)
            if self.instance and self.instance.key in SystemSettingAdmin.KIOSK_PRINTER_PROFILE_MAP_KEYS:
                return SystemSettingAdmin._clean_kiosk_printer_profile_map(value)
            return value

    form = Form

    COLOR_KEYS = {
        "first_name_color",
        "last_name_color",
        "kiosk_background_color",
        "kiosk_background_color_darkmode",
    }
    FRIENDLY_LABELS = {
        "enable_google_fonts": "Enable Google Fonts for Kiosk Heading",
        "first_name_color": "First Name Color",
        "hide_last_name": "Hide Last Name",
        "kiosk_background_color": "Kiosk Background Color (Light)",
        "kiosk_background_color_darkmode": "Kiosk Background Color (Dark)",
        "kiosk_logo_path": "Kiosk Logo Image",
        "kiosk_logo_width_px": "Kiosk Logo Width (px)",
        "kiosk_logo_height_px": "Kiosk Logo Height (px)",
        "kiosk_print_mode": "Auto Print Mode",
        "kiosk_print_iframe": "In-Page Print Preview Mode",
        "print_mode": "Printer Mode",
        "printnode_api_key": "PrintNode API Key",
        "printnode_label_width_in": "Label Width (in)",
        "printnode_label_height_in": "Label Height (in)",
        "printnode_label_margin_in": "Label Margin (in)",
        "brother_label_media": "Brother Label Media",
        "printer_profiles": "Printer Profiles",
        "kiosk_printer_profile_map": "Kiosk Printer Profile Map",
        "printnode_printer_map": "PrintNode Kiosk Printer Map",
        "server_printer_map": "Server Kiosk Printer Map",
        "server_printer_timeout_seconds": "Server Printer Timeout (seconds)",
        "admin_skin": "Admin Skin",
        "label_font": "Label Font",
        "label_first_name_scale": "Label First Name Size (%)",
        "label_last_name_scale": "Label Last Name Size (%)",
        "last_name_color": "Last Name Color",
        "welcome_heading": "Welcome Heading Text",
        "welcome_heading_font": "Welcome Heading Font",
        "welcome_heading_font_source": "Welcome Heading Font Source",
    }
    SECTION_ORDER = [
        "Kiosk Preferences",
        "Kiosk Font Loading",
        "Admin Appearance",
        "Label & Printing",
        "Printing Backends",
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
        "Kiosk Font Loading": {"enable_google_fonts"},
        "Label & Printing": {
            "first_name_color",
            "last_name_color",
            "hide_last_name",
            "label_font",
            "label_first_name_scale",
            "label_last_name_scale",
            "printnode_label_width_in",
            "printnode_label_height_in",
            "printnode_label_margin_in",
            "brother_label_media",
            "kiosk_print_mode",
            "kiosk_print_iframe",
        },
        "Printing Backends": {
            "print_mode",
            "printer_profiles",
            "kiosk_printer_profile_map",
            "printnode_api_key",
            "printnode_printer_map",
            "server_printer_map",
            "server_printer_timeout_seconds",
        },
        "Admin Appearance": {"admin_skin"},
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
            ),
            path(
                "verify-printnode-api-key/",
                self.admin_site.admin_view(self.verify_printnode_api_key_view),
                name="core_systemsetting_verify_printnode_api_key",
            ),
        ]
        return custom_urls + urls

    def verify_printnode_api_key_view(self, request):
        if not can_manage_configuration(request.user):
            return JsonResponse({"ok": False, "message": "Permission denied."}, status=403)
        if request.method != "POST":
            return JsonResponse({"ok": False, "message": "POST required."}, status=405)
        ok, message = verify_printnode_api_key(request.POST.get("api_key"))
        return JsonResponse({"ok": ok, "message": message}, status=200 if ok else 400)

    def bulk_edit_view(self, request):
        if not can_manage_configuration(request.user):
            return redirect("/admin/")
        settings_qs = list(SystemSetting.objects.order_by("key"))
        field_to_setting = {f"setting_{item.id}": item for item in settings_qs}

        class BulkSettingsForm(forms.Form):
            def clean(self_inner):
                cleaned_data = super().clean()
                for form_field_name, form_setting_obj in field_to_setting.items():
                    if form_setting_obj.key in SystemSettingAdmin.PRINTNODE_PRINTER_MAP_KEYS and form_field_name in cleaned_data:
                        cleaned_data[form_field_name] = SystemSettingAdmin._clean_printer_map(
                            cleaned_data.get(form_field_name)
                        )
                    if form_setting_obj.key in SystemSettingAdmin.SERVER_PRINTER_MAP_KEYS and form_field_name in cleaned_data:
                        cleaned_data[form_field_name] = SystemSettingAdmin._clean_server_printer_map(
                            cleaned_data.get(form_field_name)
                        )
                    if form_setting_obj.key in SystemSettingAdmin.PRINTER_PROFILE_KEYS and form_field_name in cleaned_data:
                        cleaned_data[form_field_name] = SystemSettingAdmin._clean_printer_profiles(
                            cleaned_data.get(form_field_name)
                        )
                    if form_setting_obj.key in SystemSettingAdmin.KIOSK_PRINTER_PROFILE_MAP_KEYS and form_field_name in cleaned_data:
                        cleaned_data[form_field_name] = SystemSettingAdmin._clean_kiosk_printer_profile_map(
                            cleaned_data.get(form_field_name)
                        )
                return cleaned_data

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
                choices = SYSTEM_FONT_CHOICES if setting_obj.key == "label_font" else ALL_FONT_CHOICES
                field = forms.ChoiceField(
                    choices=choices,
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
                    help_text=format_html(
                        'Preview available skins in the <a href="{}" target="_blank" rel="noopener noreferrer">Jazzmin UI docs</a>.',
                        self.ADMIN_SKIN_PREVIEW_URL,
                    ),
                )
            elif setting_obj.key in self.PRINT_MODE_KEYS:
                field = forms.ChoiceField(
                    choices=self.PRINT_MODE_CHOICES,
                    initial=initial_value or PRINT_MODE_CONNECTED,
                    required=False,
                    label=setting_obj.key,
                    widget=forms.Select(attrs={"class": "vSelect"}),
                )
            elif setting_obj.key in self.BROTHER_MEDIA_KEYS:
                field = forms.ChoiceField(
                    choices=self.BROTHER_MEDIA_CHOICES,
                    initial=initial_value or "62red",
                    required=False,
                    label=setting_obj.key,
                    widget=forms.Select(attrs={"class": "vSelect"}),
                )
            elif setting_obj.key in self.SECRET_KEYS:
                field = forms.CharField(
                    initial=initial_value,
                    required=False,
                    label=setting_obj.key,
                    widget=forms.PasswordInput(attrs={"class": "vTextField"}, render_value=True),
                    help_text="Stored locally in the database. Leave blank to disable PrintNode printing.",
                )
            elif setting_obj.key in self.JSON_KEYS:
                try:
                    parsed_initial = json.loads(initial_value or "{}")
                except json.JSONDecodeError:
                    parsed_initial = initial_value or "{}"
                help_text = 'Example: {"kiosk1": "123456", "kiosk2": "123457"}'
                if setting_obj.key in self.SERVER_PRINTER_MAP_KEYS:
                    help_text = 'Examples: {"kiosk1": "queue:Brother_QL_820NWB"} or {"kiosk1": "192.168.1.50:9100"}. Queue mode uses the server computer print queue.'
                if setting_obj.key in self.PRINTER_PROFILE_KEYS:
                    help_text = 'Example: {"front-desk-brother": {"backend": "server", "target": "queue:Brother_QL_820NWB", "label_width_in": "2.440", "label_height_in": "1.1", "brother_label_media": "62red"}}'
                if setting_obj.key in self.KIOSK_PRINTER_PROFILE_MAP_KEYS:
                    help_text = 'Example: {"kiosk1": "front-desk-brother", "kiosk2": "side-door-zebra"}. Existing direct printer maps are still used when a kiosk has no profile.'
                field = forms.JSONField(
                    initial=parsed_initial,
                    required=False,
                    label=setting_obj.key,
                    widget=forms.Textarea(attrs={"class": "vLargeTextField", "rows": 6}),
                    help_text=help_text,
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
            elif setting_obj.key in self.DECIMAL_KEYS:
                field = forms.DecimalField(
                    initial=initial_value or "",
                    required=False,
                    min_value=0,
                    max_value=10,
                    decimal_places=3,
                    max_digits=5,
                    label=setting_obj.key,
                    widget=forms.NumberInput(attrs={"class": "vTextField", "step": "0.001", "placeholder": "1.102"}),
                    help_text="Measurement in inches.",
                )
            elif setting_obj.key in self.INT_KEYS:
                cleaned_initial = initial_value if str(initial_value).isdigit() else "10"
                field = forms.IntegerField(
                    initial=cleaned_initial,
                    required=False,
                    min_value=1,
                    max_value=60,
                    label=setting_obj.key,
                    widget=forms.NumberInput(attrs={"class": "vTextField", "placeholder": "10"}),
                    help_text="Whole seconds from 1 to 60.",
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
                    elif setting_obj.key in self.JSON_KEYS:
                        new_value = json.dumps(raw_value or {}, indent=2, sort_keys=True)
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
                        metadata={
                            "key": setting_obj.key,
                            "old_value": self._audit_value(setting_obj, old_value),
                            "new_value": self._audit_value(setting_obj, new_value),
                        },
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
            "selected_print_mode": get_setting("print_mode", PRINT_MODE_CONNECTED),
            "printnode_selected": get_setting("print_mode", PRINT_MODE_CONNECTED) == PRINT_MODE_PRINTNODE,
            "verify_printnode_url": reverse("admin:core_systemsetting_verify_printnode_api_key"),
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
        if obj.key in self.JSON_KEYS:
            obj.value = json.dumps(form.cleaned_data.get("value") or {}, indent=2, sort_keys=True)
        super().save_model(request, obj, form, change)
        new_value = obj.value or ""
        if not change or str(old_value) != str(new_value):
            log_event(
                AuditLog.ACTION_SETTING_CHANGE,
                user=request.user,
                message=f'Setting "{obj.key}" updated.',
                metadata={
                    "key": obj.key,
                    "old_value": self._audit_value(obj, old_value),
                    "new_value": self._audit_value(obj, new_value),
                },
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
