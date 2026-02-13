import re

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .countries import COUNTRIES

class Family(models.Model):
    name = models.CharField(max_length=200)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Families"

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.name:
            self.name = re.sub(r"\s+family\s*$", "", self.name.strip(), flags=re.IGNORECASE)

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class Person(models.Model):
    MEMBER = "member"
    VISITOR = "visitor"
    MEMBER_TYPES = [
        (MEMBER, "Member"),
        (VISITOR, "Visitor"),
    ]

    first_name = models.CharField(max_length=120)
    middle_initial = models.CharField(max_length=1, blank=True)
    last_name = models.CharField(max_length=120)
    street_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state_province = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(
        max_length=100,
        choices=COUNTRIES,
        default="United States of America",
        blank=True,
    )
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    confidential_notes = models.TextField(blank=True)
    birth_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    birth_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    photo = models.FileField(upload_to="people/photos/", blank=True, null=True)
    member_type = models.CharField(max_length=20, choices=MEMBER_TYPES, default=VISITOR)
    family = models.ForeignKey(Family, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    tags = models.ManyToManyField("Tag", blank=True)

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "People"
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self) -> str:
        middle = f" {self.middle_initial}." if self.middle_initial else ""
        return f"{self.first_name}{middle} {self.last_name}"


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SystemSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class Service(models.Model):
    OPEN = "open"
    CLOSED = "closed"
    STATUS_CHOICES = [
        (OPEN, "Open"),
        (CLOSED, "Closed"),
    ]

    date = models.DateField()
    label = models.CharField(max_length=100, default="Sunday Service")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=OPEN)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Church Service"
        verbose_name_plural = "Church Services"
        ordering = ["-date", "label"]

    def __str__(self) -> str:
        return f"{self.label} ({self.date})"


class Attendance(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    checked_in_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-checked_in_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["person", "service"],
                name="unique_attendance_per_service",
            )
        ]

    def __str__(self) -> str:
        return f"{self.person} @ {self.service}"
