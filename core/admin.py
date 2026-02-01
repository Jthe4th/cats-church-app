from django.contrib import admin
from django.contrib.auth.models import Group
from django.http import HttpRequest, HttpResponseRedirect
from django.utils.html import format_html

from .models import Attendance, Family, Person, Service, Tag


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
    list_display = ("label", "date")
    list_filter = ("label",)
    search_fields = ("label",)
    change_form_template = "admin/core/service/change_form.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        attendees = []
        missing_members = []
        first_time_visitors = []
        if object_id:
            service = Service.objects.filter(id=object_id).first()
            attendees = list(
                Attendance.objects.filter(service_id=object_id)
                .select_related("person")
                .order_by("person__last_name", "person__first_name")
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
        extra_context["attendees"] = attendees
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
