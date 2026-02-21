from .models import AuditLog


def log_event(action, *, user=None, service=None, person=None, attendance=None, message="", metadata=None):
    AuditLog.objects.create(
        action=action,
        actor=user if getattr(user, "is_authenticated", False) else None,
        service=service,
        person=person,
        attendance=attendance,
        message=message,
        metadata=metadata or {},
    )
