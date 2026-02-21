from datetime import date, timedelta
import re

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Max, Min, Q
import csv

from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .audit import log_event
from .fonts import GOOGLE_FONT_HREFS, SYSTEM_FONT_CHOICES
from .forms import PersonForm
from .models import Attendance, AuditLog, Family, Person, Service
from .permissions import can_access_kiosk, can_access_staff_views, can_print_labels, can_view_confidential_notes
from .settings_store import get_setting


def _service_label(service_date: date) -> str:
    return f"Sabbath Service {service_date.strftime('%m-%d-%Y')}"


def _safe_hex_color(value: str, default: str) -> str:
    if value and re.match(r"^#[0-9a-fA-F]{6}$", value):
        return value
    return default


def _safe_px_size(value: str, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, 1200)


def _safe_percent_scale(value: str, default: int = 100) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed < 50:
        return 50
    if parsed > 200:
        return 200
    return parsed


SYSTEM_FONT_SET = {name for name, _label in SYSTEM_FONT_CHOICES}


def _is_yes(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"yes", "true", "1"}


def _resolve_font(font_name: str, source: str, enable_google_fonts: bool, fallback: str = "Arial"):
    font_name = (font_name or "").strip()
    source = (source or "system").strip().lower()
    if source == "google" and enable_google_fonts:
        href = GOOGLE_FONT_HREFS.get(font_name)
        if href:
            return f'"{font_name}", Arial, sans-serif', href
    # Auto-detect Google fonts even if source is accidentally left as "system".
    if source == "system" and enable_google_fonts:
        href = GOOGLE_FONT_HREFS.get(font_name)
        if href:
            return f'"{font_name}", Arial, sans-serif', href
    if font_name in SYSTEM_FONT_SET:
        return f'"{font_name}", Arial, sans-serif', None
    return f'"{fallback}", Arial, sans-serif', None


def admin_root_redirect(request):
    if request.user.is_authenticated and can_access_staff_views(request.user):
        open_service = Service.objects.filter(status=Service.OPEN).order_by("-date", "-id").first()
        active_service = open_service or Service.objects.order_by("-date", "-id").first()
        attendee_count = 0
        first_time_count = 0
        missing_count = 0
        checkin_pace = None
        last_checkin_at = None
        if active_service:
            attended_ids = list(
                Attendance.objects.filter(service=active_service).values_list("person_id", flat=True)
            )
            attendee_count = len(attended_ids)
            if attended_ids:
                prior_attendance_ids = set(
                    Attendance.objects.filter(
                        person_id__in=attended_ids,
                        service__date__lt=active_service.date,
                    ).values_list("person_id", flat=True)
                )
                first_time_count = (
                    Person.objects.filter(id__in=attended_ids, member_type=Person.VISITOR)
                    .exclude(id__in=prior_attendance_ids)
                    .count()
                )
            missing_count = (
                Person.objects.filter(member_type=Person.MEMBER, is_active=True)
                .exclude(id__in=attended_ids)
                .count()
            )
            attendance_window = Attendance.objects.filter(service=active_service).aggregate(
                first_checkin=Min("checked_in_at"),
                last_checkin=Max("checked_in_at"),
            )
            last_checkin_at = attendance_window.get("last_checkin")
            first_checkin_at = attendance_window.get("first_checkin")
            if first_checkin_at and attendee_count:
                elapsed_hours = max((timezone.now() - first_checkin_at).total_seconds() / 3600, 0.1)
                checkin_pace = round(attendee_count / elapsed_hours, 1)

        recent_services = list(Service.objects.order_by("-date", "-id")[:8])
        recent_service_ids = [service.id for service in recent_services]
        recent_counts = {
            row["service_id"]: row
            for row in Attendance.objects.filter(service_id__in=recent_service_ids)
            .values("service_id")
            .annotate(
                total=Count("id"),
                members=Count("id", filter=Q(person__member_type=Person.MEMBER)),
                visitors=Count("id", filter=Q(person__member_type=Person.VISITOR)),
            )
        }
        trend_points = []
        for service in reversed(recent_services):
            counts = recent_counts.get(service.id, {})
            attended_ids = list(Attendance.objects.filter(service=service).values_list("person_id", flat=True))
            first_time_visitors = 0
            if attended_ids:
                prior_attendance_ids = Attendance.objects.filter(
                    person_id__in=attended_ids,
                    service__date__lt=service.date,
                ).values_list("person_id", flat=True)
                first_time_visitors = (
                    Person.objects.filter(id__in=attended_ids, member_type=Person.VISITOR)
                    .exclude(id__in=prior_attendance_ids)
                    .count()
                )
            trend_points.append(
                {
                    "label": service.date.strftime("%m/%d"),
                    "total": counts.get("total", 0),
                    "first_time": first_time_visitors,
                    "members": counts.get("members", 0),
                    "visitors": counts.get("visitors", 0),
                }
            )

        max_attendance = max([point["total"] for point in trend_points], default=0)
        max_first_time = max([point["first_time"] for point in trend_points], default=0)
        for point in trend_points:
            point["total_pct"] = int((point["total"] / max_attendance) * 100) if max_attendance else 0
            point["first_time_pct"] = int((point["first_time"] / max_first_time) * 100) if max_first_time else 0
            total = point["members"] + point["visitors"]
            point["member_pct"] = int((point["members"] / total) * 100) if total else 0
            point["visitor_pct"] = int((point["visitors"] / total) * 100) if total else 0

        recent_two_services = list(Service.objects.order_by("-date", "-id")[:2])
        recent_two_ids = [service.id for service in recent_two_services]
        attended_recent_two = Attendance.objects.filter(service_id__in=recent_two_ids).values_list("person_id", flat=True)
        at_risk_count = (
            Person.objects.filter(member_type=Person.MEMBER, is_active=True)
            .exclude(id__in=attended_recent_two)
            .count()
        )

        first_time_followup = []
        if active_service:
            active_attended = Attendance.objects.filter(service=active_service).values_list("person_id", flat=True)
            prior_active = Attendance.objects.filter(
                person_id__in=active_attended, service__date__lt=active_service.date
            ).values_list("person_id", flat=True)
            first_time_followup = list(
                Person.objects.filter(id__in=active_attended, member_type=Person.VISITOR)
                .exclude(id__in=prior_active)
                .order_by("last_name", "first_name")[:6]
            )
        context = {
            **admin.site.each_context(request),
            "title": "Welcome System Dashboard",
            "open_service": open_service,
            "active_service": active_service,
            "attendee_count": attendee_count,
            "first_time_count": first_time_count,
            "missing_count": missing_count,
            "person_count": Person.objects.count(),
            "family_count": Family.objects.count(),
            "services_count": Service.objects.count(),
            "checkin_pace": checkin_pace,
            "last_checkin_at": last_checkin_at,
            "trend_points": trend_points,
            "at_risk_count": at_risk_count,
            "first_time_followup": first_time_followup,
        }
        return render(request, "admin/home.html", context)
    login_url = reverse("admin:login")
    return redirect(f"{login_url}?next=/admin/")


def healthz(request):
    return JsonResponse({"ok": True})


def _get_or_create_service() -> Service:
    today = date.today()
    service, _created = Service.objects.get_or_create(
        date=today,
        label=_service_label(today),
    )
    return service


def _is_current_service_open() -> bool:
    return _get_or_create_service().status == Service.OPEN


def kiosk_status(request):
    if not can_access_kiosk(request.user):
        return JsonResponse({"service_open": False, "service_label": "", "logout": True}, status=403)
    service = _get_or_create_service()
    return JsonResponse(
        {
            "service_open": service.status == Service.OPEN,
            "service_label": service.label if service.status == Service.OPEN else "",
            "logout": False,
        }
    )


def checkin(request, *, kiosk_mode: bool = False):
    query = request.GET.get("q", "").strip()
    match_groups = []
    auto_print = get_setting("kiosk_print_mode", "No").strip().lower() in {"yes", "true", "1"}
    iframe_print = get_setting("kiosk_print_iframe", "No").strip().lower() in {"yes", "true", "1"}
    enable_google_fonts = _is_yes(get_setting("enable_google_fonts", "Yes"), default=True)
    welcome_heading_font_family, welcome_heading_font_href = _resolve_font(
        get_setting("welcome_heading_font", "Arial"),
        get_setting("welcome_heading_font_source", "system"),
        enable_google_fonts,
        fallback="Arial",
    )
    if query:
        match_groups = _build_match_groups(query)
    current_service = _get_or_create_service()
    logo_width = _safe_px_size(get_setting("kiosk_logo_width_px", "200"), 200)
    logo_height = _safe_px_size(get_setting("kiosk_logo_height_px", "0"), 0)
    logo_path = get_setting("kiosk_logo_path", "/static/img/EC-SDA-Church_Stacked_Final.png") or "/static/img/EC-SDA-Church_Stacked_Final.png"

    if request.method == "POST":
        if kiosk_mode and not _is_current_service_open():
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"service_closed": True, "message": "This service is closed."}, status=423)
            return redirect("/kiosk/logout/?service_closed=1")
        action = request.POST.get("action")
        if action in {"print_selected", "check_in_selected"}:
            person_ids = [pid for pid in request.POST.getlist("person_ids") if pid.isdigit()]
            if not person_ids:
                primary_id = request.POST.get("primary_person_id")
                if primary_id and primary_id.isdigit():
                    person_ids = [primary_id]
            if person_ids:
                service = _get_or_create_service()
                attendance_ids = []
                for person_id in person_ids:
                    person = get_object_or_404(Person, pk=int(person_id))
                    attendance, _created = Attendance.objects.get_or_create(
                        person=person,
                        service=service,
                    )
                    if _created:
                        log_event(
                            AuditLog.ACTION_CHECKIN,
                            user=request.user,
                            service=service,
                            person=person,
                            attendance=attendance,
                            message="Checked in from kiosk selection flow.",
                        )
                    attendance_ids.append(attendance.id)
                ids_param = ",".join(str(aid) for aid in attendance_ids)
                if action == "check_in_selected":
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({"checked_in": True, "count": len(attendance_ids)})
                    return redirect("kiosk" if kiosk_mode else "checkin")
                auto_param = "&auto=1" if auto_print else ""
                print_url = f"/print-batch/?ids={ids_param}{auto_param}"
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({"print_url": print_url})
                return redirect(print_url)
        else:
            person_id = request.POST.get("person_id")
            if person_id:
                person = get_object_or_404(Person, pk=person_id)
            else:
                first_name = request.POST.get("first_name", "").strip()
                middle_initial = request.POST.get("middle_initial", "").strip()
                last_name = request.POST.get("last_name", "").strip()
                street_address = request.POST.get("street_address", "").strip()
                phone = request.POST.get("phone", "").strip()
                email = request.POST.get("email", "").strip()
                birth_month_raw = request.POST.get("birth_month", "").strip()
                birth_day_raw = request.POST.get("birth_day", "").strip()
                birth_month = int(birth_month_raw) if birth_month_raw.isdigit() else None
                birth_day = int(birth_day_raw) if birth_day_raw.isdigit() else None
                person = Person.objects.create(
                    first_name=first_name,
                    middle_initial=middle_initial,
                    last_name=last_name,
                    street_address=street_address,
                    phone=phone,
                    email=email,
                    birth_month=birth_month,
                    birth_day=birth_day,
                    member_type=Person.VISITOR,
                )

            service = _get_or_create_service()
            attendance, _created = Attendance.objects.get_or_create(
                person=person,
                service=service,
            )
            if _created:
                log_event(
                    AuditLog.ACTION_CHECKIN,
                    user=request.user,
                    service=service,
                    person=person,
                    attendance=attendance,
                    message="Checked in from kiosk single-person flow.",
                )
            if action == "check_in_only":
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({"checked_in": True, "count": 1})
                return redirect("kiosk" if kiosk_mode else "checkin")
            url = reverse("print_tag", kwargs={"attendance_id": attendance.id})
            if auto_print:
                url = f"{url}?auto=1"
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"print_url": url})
            return redirect(url)

    return render(
        request,
        "kiosk/checkin.html",
        {
            "query": query,
            "match_groups": match_groups,
            "kiosk_mode": kiosk_mode,
            "iframe_print": iframe_print,
            "app_version": settings.CATS_VERSION,
            "kiosk_background_color": _safe_hex_color(
                get_setting("kiosk_background_color", "#ffffff"),
                "#ffffff",
            ),
            "kiosk_background_color_darkmode": _safe_hex_color(
                get_setting("kiosk_background_color_darkmode", "#000000"),
                "#000000",
            ),
            "welcome_heading": get_setting("welcome_heading", "Welcome") or "Welcome",
            "welcome_heading_font_family": welcome_heading_font_family,
            "google_font_hrefs": [welcome_heading_font_href] if welcome_heading_font_href else [],
            "service_open": current_service.status == Service.OPEN,
            "service_label": current_service.label if current_service.status == Service.OPEN else "",
            "kiosk_logo_path": logo_path,
            "kiosk_logo_width_px": logo_width,
            "kiosk_logo_height_px": logo_height,
        },
    )


def kiosk(request):
    if not can_access_kiosk(request.user):
        return _kiosk_login(request)
    if not _is_current_service_open():
        return redirect("/kiosk/logout/?service_closed=1")
    return checkin(request, kiosk_mode=True)


@login_required
def kiosk_search_groups(request):
    if not can_access_kiosk(request.user):
        return JsonResponse({"groups": []}, status=403)
    if not _is_current_service_open():
        return JsonResponse({"groups": [], "service_closed": True}, status=423)
    query = request.GET.get("q", "").strip()
    if len(query) < 3:
        return JsonResponse({"groups": []})
    service = _get_or_create_service()
    groups_raw = _build_match_groups(query)
    person_ids = [member.id for group in groups_raw for member in group["members"]]
    attended_ids = set(
        Attendance.objects.filter(service=service, person_id__in=person_ids).values_list("person_id", flat=True)
    )
    groups = []
    for group in groups_raw:
        groups.append(
            {
                "family_name": group["family"].name if group["family"] else "",
                "primary_id": group["primary"].id,
                "members": [
                    {
                        "id": member.id,
                        "name": f"{member.first_name} {member.last_name}",
                        "checked_in": member.id in attended_ids,
                    }
                    for member in group["members"]
                ],
            }
        )
    return JsonResponse({"groups": groups})


def kiosk_logout(request):
    logout(request)
    if request.GET.get("service_closed") == "1":
        return redirect("/kiosk/?service_closed=1")
    return redirect("kiosk")


@login_required
def admin_quick_logout(request):
    logout(request)
    return redirect("/admin/login/")


def _kiosk_login(request):
    error = "Service is closed. Ask staff to reopen it in Admin." if request.GET.get("service_closed") == "1" else ""
    enable_google_fonts = _is_yes(get_setting("enable_google_fonts", "Yes"), default=True)
    welcome_heading_font_family, welcome_heading_font_href = _resolve_font(
        get_setting("welcome_heading_font", "Arial"),
        get_setting("welcome_heading_font_source", "system"),
        enable_google_fonts,
        fallback="Arial",
    )
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user and can_access_kiosk(user):
            if not _is_current_service_open():
                error = "Service is closed. Ask staff to reopen it in Admin."
            else:
                login(request, user)
                return redirect("kiosk")
        if user:
            error = "Access requires a Greeter or Admin role."
        else:
            error = "Invalid username or password."
    return render(
        request,
        "kiosk/login.html",
        {
            "error": error,
            "app_version": settings.CATS_VERSION,
            "kiosk_background_color": _safe_hex_color(
                get_setting("kiosk_background_color", "#ffffff"),
                "#ffffff",
            ),
            "kiosk_background_color_darkmode": _safe_hex_color(
                get_setting("kiosk_background_color_darkmode", "#000000"),
                "#000000",
            ),
            "welcome_heading": get_setting("welcome_heading", "Welcome") or "Welcome",
            "welcome_heading_font_family": welcome_heading_font_family,
            "google_font_hrefs": [welcome_heading_font_href] if welcome_heading_font_href else [],
            "kiosk_logo_path": get_setting("kiosk_logo_path", "/static/img/EC-SDA-Church_Stacked_Final.png")
            or "/static/img/EC-SDA-Church_Stacked_Final.png",
            "kiosk_logo_width_px": _safe_px_size(get_setting("kiosk_logo_width_px", "200"), 200),
            "kiosk_logo_height_px": _safe_px_size(get_setting("kiosk_logo_height_px", "0"), 0),
        },
    )


def _build_match_groups(query: str):
    filters = Q(first_name__icontains=query) | Q(last_name__icontains=query)
    if query.isdigit() and len(query) == 4:
        filters |= Q(phone__icontains=query)
    matches = (
        Person.objects.filter(filters)
        .select_related("family")
        .prefetch_related("family__person_set")
        .order_by("last_name", "first_name")
    )
    groups = []
    seen_family_ids = set()
    for person in matches:
        if person.family_id:
            if person.family_id in seen_family_ids:
                continue
            seen_family_ids.add(person.family_id)
            groups.append(
                {
                    "family": person.family,
                    "members": list(person.family.person_set.all().order_by("last_name", "first_name")),
                    "primary": person,
                }
            )
        else:
            groups.append(
                {
                    "family": None,
                    "members": [person],
                    "primary": person,
                }
            )
    return groups


@login_required
@user_passes_test(can_print_labels)
@xframe_options_sameorigin
def print_tag(request, attendance_id: int):
    attendance = get_object_or_404(Attendance, pk=attendance_id)
    log_event(
        AuditLog.ACTION_PRINT,
        user=request.user,
        service=attendance.service,
        person=attendance.person,
        attendance=attendance,
        message="Single nametag print requested.",
        metadata={"mode": "single"},
    )
    hide_last_name = get_setting("hide_last_name", "No").strip().lower() in {"yes", "true", "1"}
    enable_google_fonts = _is_yes(get_setting("enable_google_fonts", "Yes"), default=True)
    label_font_family, label_font_href = _resolve_font(
        get_setting("label_font", "Arial"),
        get_setting("label_font_source", "system"),
        enable_google_fonts,
        fallback="Arial",
    )
    auto_print = request.GET.get("auto") == "1"
    iframe_mode = request.GET.get("iframe") == "1"
    first_scale = _safe_percent_scale(get_setting("label_first_name_scale", "100"), 100)
    last_scale = _safe_percent_scale(get_setting("label_last_name_scale", "100"), 100)
    next_raw = request.GET.get("next", "")
    next_ids = [value for value in next_raw.split(",") if value.isdigit()]
    next_url = ""
    if next_ids:
        next_id = int(next_ids[0])
        remaining = ",".join(next_ids[1:])
        params = []
        if auto_print:
            params.append("auto=1")
        if iframe_mode:
            params.append("iframe=1")
        if remaining:
            params.append(f"next={remaining}")
        query = "&".join(params)
        next_url = reverse("print_tag", kwargs={"attendance_id": next_id})
        if query:
            next_url = f"{next_url}?{query}"
    return render(
        request,
        "kiosk/print.html",
        {
            "attendance": attendance,
            "first_name_color": get_setting("first_name_color", "#000000"),
            "last_name_color": get_setting("last_name_color", "#000000"),
            "hide_last_name": hide_last_name,
            "label_font_family": label_font_family,
            "google_font_hrefs": [label_font_href] if label_font_href else [],
            "auto_print": auto_print,
            "next_url": next_url,
            "iframe_mode": iframe_mode,
            "label_first_name_scale_factor": f"{first_scale / 100:.2f}",
            "label_last_name_scale_factor": f"{last_scale / 100:.2f}",
        },
    )


@login_required
@user_passes_test(can_print_labels)
@xframe_options_sameorigin
def print_batch(request):
    ids_raw = request.GET.get("ids", "")
    ids = [int(value) for value in ids_raw.split(",") if value.isdigit()]
    attendances = list(Attendance.objects.filter(id__in=ids).select_related("person", "service"))
    attendance_by_id = {att.id: att for att in attendances}
    ordered = [attendance_by_id[att_id] for att_id in ids if att_id in attendance_by_id]
    hide_last_name = get_setting("hide_last_name", "No").strip().lower() in {"yes", "true", "1"}
    enable_google_fonts = _is_yes(get_setting("enable_google_fonts", "Yes"), default=True)
    label_font_family, label_font_href = _resolve_font(
        get_setting("label_font", "Arial"),
        get_setting("label_font_source", "system"),
        enable_google_fonts,
        fallback="Arial",
    )
    auto_print = request.GET.get("auto") == "1"
    iframe_mode = request.GET.get("iframe") == "1"
    first_scale = _safe_percent_scale(get_setting("label_first_name_scale", "100"), 100)
    last_scale = _safe_percent_scale(get_setting("label_last_name_scale", "100"), 100)
    ua = request.META.get("HTTP_USER_AGENT", "")
    serial = request.GET.get("serial") == "1"
    if not serial and "Chrome/109" in ua and "Windows NT 6.1" in ua:
        serial = True
    if serial and ordered:
        ids_list = [att.id for att in ordered]
        first_id = ids_list[0]
        remaining = ",".join(str(att_id) for att_id in ids_list[1:])
        params = []
        if auto_print:
            params.append("auto=1")
        if iframe_mode:
            params.append("iframe=1")
        if remaining:
            params.append(f"next={remaining}")
        query = "&".join(params)
        url = reverse("print_tag", kwargs={"attendance_id": first_id})
        if query:
            url = f"{url}?{query}"
        return redirect(url)
    if ordered:
        log_event(
            AuditLog.ACTION_PRINT,
            user=request.user,
            service=ordered[0].service,
            message="Batch nametag print requested.",
            metadata={"attendance_ids": [att.id for att in ordered], "count": len(ordered), "mode": "batch"},
        )
    return render(
        request,
        "kiosk/print_batch.html",
        {
            "attendances": ordered,
            "first_name_color": get_setting("first_name_color", "#000000"),
            "last_name_color": get_setting("last_name_color", "#000000"),
            "hide_last_name": hide_last_name,
            "label_font_family": label_font_family,
            "google_font_hrefs": [label_font_href] if label_font_href else [],
            "auto_print": auto_print,
            "iframe_mode": iframe_mode,
            "label_first_name_scale_factor": f"{first_scale / 100:.2f}",
            "label_last_name_scale_factor": f"{last_scale / 100:.2f}",
        },
    )


@login_required
@user_passes_test(can_access_staff_views)
def missing_members_report(request):
    service = Service.objects.order_by("-date", "label").first()
    missing_members = []
    if service:
        attended_ids = Attendance.objects.filter(service=service).values_list("person_id", flat=True)
        missing_members = (
            Person.objects.filter(member_type=Person.MEMBER, is_active=True)
            .exclude(id__in=attended_ids)
            .order_by("last_name", "first_name")
        )
        if request.GET.get("format") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="missing_members_{service.date}.csv"'
            response.write("\ufeff")  # UTF-8 BOM for Excel compatibility
            writer = csv.writer(response)
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
            for person in missing_members:
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
    return render(
        request,
        "admin/missing_members.html",
        {"service": service, "missing_members": missing_members},
    )

@login_required
@user_passes_test(can_access_staff_views)
def staff_people(request):
    query = request.GET.get("q", "").strip()
    people = Person.objects.all().order_by("last_name", "first_name")
    if query:
        people = people.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(email__icontains=query)
        )

    return render(request, "staff/people_list.html", {"people": people, "query": query})


@login_required
@user_passes_test(can_access_staff_views)
def staff_person(request, person_id: int):
    person = get_object_or_404(Person, pk=person_id)
    include_confidential = can_view_confidential_notes(request.user)
    if request.method == "POST":
        form = PersonForm(
            request.POST,
            request.FILES,
            instance=person,
            include_confidential=include_confidential,
        )
        if form.is_valid():
            form.save()
            return redirect("staff_person", person_id=person.id)
    else:
        form = PersonForm(instance=person, include_confidential=include_confidential)

    return render(request, "staff/person_edit.html", {"person": person, "form": form})


@login_required
@user_passes_test(can_access_staff_views)
def staff_people_search(request):
    query = request.GET.get("q", "").strip()
    results = []
    if len(query) >= 3:
        people = (
            Person.objects.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query))
            .select_related("family")
            .order_by("last_name", "first_name")[:12]
        )
        results = [
            {
                "id": person.id,
                "name": f"{person.first_name} {person.last_name}",
                "family": person.family.name if person.family else "",
            }
            for person in people
        ]
    return JsonResponse({"results": results})


@login_required
@user_passes_test(can_access_staff_views)
def staff_people_search_groups(request):
    query = request.GET.get("q", "").strip()
    groups = []
    if len(query) >= 3:
        matches = (
            Person.objects.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query))
            .select_related("family")
            .prefetch_related("family__person_set")
            .order_by("last_name", "first_name")
        )
        seen_family_ids = set()
        for person in matches:
            if person.family_id:
                if person.family_id in seen_family_ids:
                    continue
                seen_family_ids.add(person.family_id)
                members = list(person.family.person_set.all().order_by("last_name", "first_name"))
                groups.append(
                    {
                        "family_name": person.family.name,
                        "primary_id": person.id,
                        "members": [
                            {"id": member.id, "name": f"{member.first_name} {member.last_name}"}
                            for member in members
                        ],
                    }
                )
            else:
                groups.append(
                    {
                        "family_name": "",
                        "primary_id": person.id,
                        "members": [{"id": person.id, "name": f"{person.first_name} {person.last_name}"}],
                    }
                )
            if len(groups) >= 12:
                break
    return JsonResponse({"groups": groups})


@login_required
@user_passes_test(can_access_staff_views)
def admin_print_selected(request):
    if request.method != "POST":
        return redirect("/admin/")
    person_ids = [pid for pid in request.POST.getlist("person_ids") if pid.isdigit()]
    if not person_ids:
        primary_id = request.POST.get("primary_person_id")
        if primary_id and primary_id.isdigit():
            person_ids = [primary_id]
    if not person_ids:
        return redirect("/admin/")

    service = _get_or_create_service()
    attendance_ids = []
    for person_id in person_ids:
        person = get_object_or_404(Person, pk=int(person_id))
        attendance, _created = Attendance.objects.get_or_create(
            person=person,
            service=service,
        )
        if _created:
            log_event(
                AuditLog.ACTION_CHECKIN,
                user=request.user,
                service=service,
                person=person,
                attendance=attendance,
                message="Checked in from admin print-selected flow.",
                metadata={"source": "admin_print_selected"},
            )
        attendance_ids.append(attendance.id)
    ids_param = ",".join(str(att_id) for att_id in attendance_ids)
    print_url = f"/print-batch/?ids={ids_param}"
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"print_url": print_url})
    return redirect(print_url)


@login_required
@user_passes_test(can_access_staff_views)
def staff_dashboard(request):
    context = admin.site.each_context(request)
    return render(request, "staff/dashboard.html", context)


@login_required
@user_passes_test(can_access_staff_views)
def audit_log_report(request):
    days_raw = request.GET.get("days", "7")
    days = int(days_raw) if days_raw.isdigit() and int(days_raw) > 0 else 7
    action = request.GET.get("action", "").strip()
    actor = request.GET.get("actor", "").strip()

    since = timezone.now() - timedelta(days=days)
    logs = AuditLog.objects.select_related("actor", "service", "person").filter(created_at__gte=since)
    if action:
        logs = logs.filter(action=action)
    if actor:
        logs = logs.filter(actor__username__icontains=actor)

    logs = logs.order_by("-created_at")[:500]

    context = {
        **admin.site.each_context(request),
        "title": "Audit Log",
        "logs": logs,
        "days": days,
        "action": action,
        "actor": actor,
        "action_choices": AuditLog.ACTION_CHOICES,
    }
    return render(request, "admin/audit_log_report.html", context)
