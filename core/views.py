from datetime import date
import re

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
import csv

from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .fonts import GOOGLE_FONT_HREFS, SYSTEM_FONT_CHOICES
from .forms import PersonForm
from .models import Attendance, Person, Service
from .settings_store import get_setting


def _service_label(service_date: date) -> str:
    return f"Sabbath Service {service_date.strftime('%m-%d-%Y')}"


def _safe_hex_color(value: str, default: str) -> str:
    if value and re.match(r"^#[0-9a-fA-F]{6}$", value):
        return value
    return default


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
    target = reverse("admin:core_service_changelist")
    if request.user.is_authenticated and request.user.is_staff:
        return redirect(target)
    login_url = reverse("admin:login")
    return redirect(f"{login_url}?next={target}")


def healthz(request):
    return JsonResponse({"ok": True})


def _get_or_create_service() -> Service:
    today = date.today()
    service, _created = Service.objects.get_or_create(
        date=today,
        label=_service_label(today),
    )
    return service


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

    if request.method == "POST":
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
        },
    )


def kiosk(request):
    if not _user_has_kiosk_access(request.user):
        return _kiosk_login(request)
    return checkin(request, kiosk_mode=True)


@login_required
def kiosk_search_groups(request):
    if not _user_has_kiosk_access(request.user):
        return JsonResponse({"groups": []}, status=403)
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
    return redirect("kiosk")


def _user_has_kiosk_access(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Greeter", "Admin"]).exists()


def _kiosk_login(request):
    error = ""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user and _user_has_kiosk_access(user):
            login(request, user)
            return redirect("kiosk")
        if user:
            error = "Access requires a Greeter or Admin role."
        else:
            error = "Invalid username or password."
    enable_google_fonts = _is_yes(get_setting("enable_google_fonts", "Yes"), default=True)
    welcome_heading_font_family, welcome_heading_font_href = _resolve_font(
        get_setting("welcome_heading_font", "Arial"),
        get_setting("welcome_heading_font_source", "system"),
        enable_google_fonts,
        fallback="Arial",
    )
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


@xframe_options_sameorigin
def print_tag(request, attendance_id: int):
    attendance = get_object_or_404(Attendance, pk=attendance_id)
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
        },
    )


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
        },
    )


def _is_staff(user) -> bool:
    return user.is_staff


def _is_pastor(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name="Pastor").exists()


@login_required
@user_passes_test(_is_staff)
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
@user_passes_test(_is_staff)
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
@user_passes_test(_is_staff)
def staff_person(request, person_id: int):
    person = get_object_or_404(Person, pk=person_id)
    include_confidential = _is_pastor(request.user)
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
@user_passes_test(_is_staff)
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
@user_passes_test(_is_staff)
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
@user_passes_test(_is_staff)
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
        attendance_ids.append(attendance.id)
    ids_param = ",".join(str(att_id) for att_id in attendance_ids)
    print_url = f"/print-batch/?ids={ids_param}"
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"print_url": print_url})
    return redirect(print_url)


@login_required
@user_passes_test(_is_staff)
def staff_dashboard(request):
    context = admin.site.each_context(request)
    return render(request, "staff/dashboard.html", context)
