from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from core import views
from core.permissions import can_access_admin_site

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),
    path("accounts/profile/", views.admin_root_redirect, name="accounts_profile_redirect"),
    path("admin/", views.admin_root_redirect, name="admin_root_redirect"),
    path("admin/quick-logout/", views.admin_quick_logout, name="admin_quick_logout"),
    path("admin/missing-members/", views.missing_members_report, name="missing_members_report"),
    path("admin/audit-log/", views.audit_log_report, name="audit_log_report"),
    path("admin/print-selected/", views.admin_print_selected, name="admin_print_selected"),
    path("admin/", admin.site.urls),
    path("staff/dashboard/", views.staff_dashboard, name="staff_dashboard"),
    path("staff/people/", views.staff_people, name="staff_people"),
    path("staff/people/<int:person_id>/", views.staff_person, name="staff_person"),
    path("staff/people/search/", views.staff_people_search, name="staff_people_search"),
    path("staff/people/search-groups/", views.staff_people_search_groups, name="staff_people_search_groups"),
    path("", views.checkin, name="checkin"),
    path("kiosk/", views.kiosk, name="kiosk"),
    path("kiosk/logout/", views.kiosk_logout, name="kiosk_logout"),
    path("kiosk/status/", views.kiosk_status, name="kiosk_status"),
    path("kiosk/search-groups/", views.kiosk_search_groups, name="kiosk_search_groups"),
    path("print/<int:attendance_id>/", views.print_tag, name="print_tag"),
    path("print-batch/", views.print_batch, name="print_batch"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.has_permission = lambda request: can_access_admin_site(request.user)
admin.site.site_header = f"Welcome System v{settings.CATS_VERSION}"
admin.site.site_title = f"Welcome System v{settings.CATS_VERSION}"
admin.site.index_title = f"Welcome System Administration v{settings.CATS_VERSION}"
