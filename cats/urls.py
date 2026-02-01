from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path("admin/missing-members/", views.missing_members_report, name="missing_members_report"),
    path("admin/print-selected/", views.admin_print_selected, name="admin_print_selected"),
    path("admin/", admin.site.urls),
    path("staff/dashboard/", views.staff_dashboard, name="staff_dashboard"),
    path("staff/people/", views.staff_people, name="staff_people"),
    path("staff/people/<int:person_id>/", views.staff_person, name="staff_person"),
    path("staff/people/search/", views.staff_people_search, name="staff_people_search"),
    path("staff/people/search-groups/", views.staff_people_search_groups, name="staff_people_search_groups"),
    path("", views.checkin, name="checkin"),
    path("kiosk/", views.kiosk, name="kiosk"),
    path("print/<int:attendance_id>/", views.print_tag, name="print_tag"),
    path("print-batch/", views.print_batch, name="print_batch"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "CATS [Church Attendance Tracking System]"
admin.site.site_title = "CATS [Church Attendance Tracking System]"
admin.site.index_title = "CATS Administration"
