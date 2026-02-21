ROLE_GREETER = "Greeter"
ROLE_ADMIN = "Admin"
ROLE_PASTOR = "Pastor"


def _has_group(user, *group_names: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=group_names).exists()


def can_access_kiosk(user) -> bool:
    return _has_group(user, ROLE_GREETER, ROLE_ADMIN)


def can_access_admin_site(user) -> bool:
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if not user.is_staff:
        return False
    return _has_group(user, ROLE_ADMIN, ROLE_PASTOR)


def can_access_staff_views(user) -> bool:
    return can_access_admin_site(user)


def can_view_confidential_notes(user) -> bool:
    return _has_group(user, ROLE_PASTOR)


def can_manage_configuration(user) -> bool:
    return _has_group(user, ROLE_ADMIN)


def can_print_labels(user) -> bool:
    return can_access_kiosk(user) or can_access_staff_views(user)
