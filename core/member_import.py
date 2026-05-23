from dataclasses import dataclass, field
import csv
from io import StringIO

from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from .models import Family, Person


MAX_IMPORT_ROWS = 1000

FIELD_ALIASES = {
    "first_name": {"first", "first name", "firstname", "given name"},
    "middle_initial": {"middle", "middle initial", "mi", "m.i."},
    "last_name": {"last", "last name", "lastname", "surname", "family name"},
    "family": {"family", "household", "household name"},
    "street_address": {"address", "street address", "street", "address 1"},
    "city": {"city"},
    "state_province": {"state", "state/province", "province", "state province"},
    "postal_code": {"zip", "zip code", "postal", "postal code"},
    "country": {"country"},
    "phone": {"phone", "phone number", "mobile", "cell"},
    "email": {"email", "email address"},
    "birth_month": {"birth month", "birthday month", "month"},
    "birth_day": {"birth day", "birthday day", "day"},
    "notes": {"notes", "note"},
    "is_active": {"active", "is active", "status"},
}


class MemberImportError(Exception):
    pass


@dataclass
class MemberImportRow:
    row_number: int
    data: dict
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    existing_person: Person | None = None

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass
class MemberImportResult:
    rows: list[MemberImportRow]
    created: int = 0
    updated: int = 0
    skipped: int = 0

    @property
    def has_errors(self) -> bool:
        return any(row.errors for row in self.rows)


def parse_member_csv(uploaded_file) -> list[MemberImportRow]:
    try:
        raw = uploaded_file.read()
    except AttributeError as exc:
        raise MemberImportError("Upload a CSV file.") from exc

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MemberImportError("The CSV file must be saved as UTF-8.") from exc

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise MemberImportError("The CSV file must include a header row.")

    header_map = _build_header_map(reader.fieldnames)
    missing_headers = [field for field in ("first_name", "last_name") if field not in header_map.values()]
    if missing_headers:
        raise MemberImportError('The CSV must include "First Name" and "Last Name" columns.')

    rows = []
    for index, raw_row in enumerate(reader, start=2):
        if len(rows) >= MAX_IMPORT_ROWS:
            raise MemberImportError(f"Import is limited to {MAX_IMPORT_ROWS} rows at a time.")
        if not any((value or "").strip() for value in raw_row.values()):
            continue
        rows.append(_clean_row(index, raw_row, header_map))

    if not rows:
        raise MemberImportError("The CSV file did not contain any member rows.")
    return rows


def import_member_rows(rows: list[MemberImportRow], *, update_existing: bool = False) -> MemberImportResult:
    result = MemberImportResult(rows=rows)
    if result.has_errors:
        raise MemberImportError("Fix validation errors before importing.")

    for row in rows:
        existing = row.existing_person or find_existing_person(row.data)
        if existing:
            if not update_existing:
                result.skipped += 1
                continue
            _update_person(existing, row.data)
            result.updated += 1
            continue
        _create_person(row.data)
        result.created += 1
    return result


def find_existing_person(data: dict) -> Person | None:
    email = data.get("email", "")
    if email:
        match = Person.objects.filter(email__iexact=email).order_by("id").first()
        if match:
            return match

    phone = data.get("phone", "")
    if phone:
        match = (
            Person.objects.filter(
                first_name__iexact=data.get("first_name", ""),
                last_name__iexact=data.get("last_name", ""),
                phone__icontains=phone[-4:] if len(phone) >= 4 else phone,
            )
            .order_by("id")
            .first()
        )
        if match:
            return match
    return None


def _build_header_map(headers) -> dict[str, str]:
    mapping = {}
    alias_to_field = {
        alias: field_name
        for field_name, aliases in FIELD_ALIASES.items()
        for alias in aliases
    }
    for header in headers:
        normalized = _normalize_header(header)
        if normalized in alias_to_field:
            mapping[header] = alias_to_field[normalized]
    return mapping


def _clean_row(row_number: int, raw_row: dict, header_map: dict) -> MemberImportRow:
    data = {field_name: "" for field_name in FIELD_ALIASES.keys()}
    for raw_header, field_name in header_map.items():
        data[field_name] = (raw_row.get(raw_header) or "").strip()

    row = MemberImportRow(row_number=row_number, data=data)
    if not data["first_name"]:
        row.errors.append("First name is required.")
    if not data["last_name"]:
        row.errors.append("Last name is required.")

    if data["middle_initial"]:
        data["middle_initial"] = data["middle_initial"][0].upper()

    if data["email"]:
        try:
            validate_email(data["email"])
        except ValidationError:
            row.errors.append("Email address is not valid.")

    for field_name, min_value, max_value, label in (
        ("birth_month", 1, 12, "Birth month"),
        ("birth_day", 1, 31, "Birth day"),
    ):
        if data[field_name]:
            if not data[field_name].isdigit():
                row.errors.append(f"{label} must be a number.")
            else:
                parsed = int(data[field_name])
                if parsed < min_value or parsed > max_value:
                    row.errors.append(f"{label} must be between {min_value} and {max_value}.")
                else:
                    data[field_name] = parsed
        else:
            data[field_name] = None

    if data["is_active"]:
        parsed_active = _parse_bool(data["is_active"])
        if parsed_active is None:
            row.errors.append('Active must be yes/no, true/false, active/inactive, or 1/0.')
        else:
            data["is_active"] = parsed_active
    else:
        data["is_active"] = True

    if not row.errors:
        row.existing_person = find_existing_person(data)
        if row.existing_person:
            row.warnings.append(f"Existing person matched: {row.existing_person}.")
        elif Person.objects.filter(first_name__iexact=data["first_name"], last_name__iexact=data["last_name"]).exists():
            row.warnings.append("Same first and last name already exists; check for duplicates.")
    return row


def _create_person(data: dict) -> Person:
    person_data = _person_fields(data)
    person_data["member_type"] = Person.MEMBER
    person_data["family"] = _get_family(data.get("family", ""))
    return Person.objects.create(**person_data)


def _update_person(person: Person, data: dict) -> Person:
    person.member_type = Person.MEMBER
    person.family = _get_family(data.get("family", "")) or person.family
    for field_name, value in _person_fields(data).items():
        if value not in ("", None) or field_name == "is_active":
            setattr(person, field_name, value)
    person.save()
    return person


def _person_fields(data: dict) -> dict:
    fields = {
        "first_name": data["first_name"],
        "middle_initial": data.get("middle_initial", ""),
        "last_name": data["last_name"],
        "street_address": data.get("street_address", ""),
        "city": data.get("city", ""),
        "state_province": data.get("state_province", ""),
        "postal_code": data.get("postal_code", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "notes": data.get("notes", ""),
        "birth_month": data.get("birth_month"),
        "birth_day": data.get("birth_day"),
        "is_active": data.get("is_active", True),
    }
    if data.get("country"):
        fields["country"] = data["country"]
    return fields


def _get_family(family_name: str) -> Family | None:
    family_name = (family_name or "").strip()
    if not family_name:
        return None
    family, _created = Family.objects.get_or_create(name=family_name)
    return family


def _normalize_header(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("_", " ").split())


def _parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"yes", "y", "true", "1", "active"}:
        return True
    if normalized in {"no", "n", "false", "0", "inactive"}:
        return False
    return None
