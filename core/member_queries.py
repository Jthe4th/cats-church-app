from django.db.models import Q, QuerySet

from .models import Person, Service


def members_active_for_service(service: Service | None) -> QuerySet[Person]:
    queryset = Person.objects.filter(member_type=Person.MEMBER, is_active=True)
    if not service:
        return queryset
    return queryset.filter(Q(created_at__isnull=True) | Q(created_at__date__lte=service.date))
