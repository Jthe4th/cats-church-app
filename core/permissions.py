ROLE_GREETER = "Greeter"
ROLE_ADMIN = "Admin"
ROLE_PASTOR = "Pastor"


def _is_active_authenticated(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active)


def _has_group(user, *group_names: str) -> bool:
    if not _is_active_authenticated(user):
        return False
    if user.is_superuser:
        return True
    target_names = {name.strip().lower() for name in group_names if (name or "").strip()}
    if not target_names:
        return False
    user_group_names = {name.strip().lower() for name in user.groups.values_list("name", flat=True)}
    return bool(user_group_names & target_names)


def can_access_kiosk(user) -> bool:
    if not _is_active_authenticated(user):
        return False
    return _has_group(user, ROLE_GREETER, ROLE_ADMIN)


def can_access_admin_site(user) -> bool:
    if not _is_active_authenticated(user):
        return False
    if not user.is_staff:
        return False
    return _has_group(user, ROLE_ADMIN, ROLE_PASTOR)


def can_access_staff_views(user) -> bool:
    if not _is_active_authenticated(user):
        return False
    if not user.is_staff:
        return False
    return _has_group(user, ROLE_ADMIN, ROLE_PASTOR)


def can_view_confidential_notes(user) -> bool:
    if not _is_active_authenticated(user):
        return False
    return _has_group(user, ROLE_PASTOR)


def can_manage_configuration(user) -> bool:
    if not _is_active_authenticated(user):
        return False
    if not user.is_staff:
        return False
    return _has_group(user, ROLE_ADMIN)


def can_print_labels(user) -> bool:
    return can_access_kiosk(user) or can_access_staff_views(user)
