import base64
import json
import re
import urllib.error
import urllib.request

from django.utils import timezone

from .models import Attendance
from .settings_store import get_setting


PRINT_MODE_CONNECTED = "Connected Printer"
PRINT_MODE_PRINTNODE = "PrintNode Printer"
PRINTNODE_API_URL = "https://api.printnode.com/printjobs"


class PrintNodeError(Exception):
    """Raised when a PrintNode job cannot be submitted."""


def is_printnode_mode() -> bool:
    return get_setting("print_mode", PRINT_MODE_CONNECTED).strip() == PRINT_MODE_PRINTNODE


def get_kiosk_printer_id(kiosk_id: str) -> int:
    kiosk_id = (kiosk_id or "").strip()
    if not kiosk_id:
        raise PrintNodeError("Missing kiosk id. Open the kiosk with ?kiosk=your-kiosk-name.")

    raw_map = get_setting("printnode_printer_map", "{}") or "{}"
    try:
        printer_map = json.loads(raw_map)
    except json.JSONDecodeError as exc:
        raise PrintNodeError("PrintNode printer map is not valid JSON.") from exc

    if not isinstance(printer_map, dict):
        raise PrintNodeError("PrintNode printer map must be a JSON object.")

    printer_id = str(printer_map.get(kiosk_id, "")).strip()
    if not printer_id:
        raise PrintNodeError(f'No PrintNode printer is configured for kiosk "{kiosk_id}".')
    if not printer_id.isdigit():
        raise PrintNodeError(f'PrintNode printer id for kiosk "{kiosk_id}" must be a number.')
    return int(printer_id)


def submit_attendance_print_job(attendance_ids, *, kiosk_id: str, user=None) -> int:
    api_key = (get_setting("printnode_api_key", "") or "").strip()
    if not api_key:
        raise PrintNodeError("PrintNode API key is not configured.")

    printer_id = get_kiosk_printer_id(kiosk_id)
    attendances = list(
        Attendance.objects.filter(id__in=attendance_ids)
        .select_related("person", "service")
        .order_by("person__last_name", "person__first_name")
    )
    attendance_by_id = {attendance.id: attendance for attendance in attendances}
    ordered = [attendance_by_id[attendance_id] for attendance_id in attendance_ids if attendance_id in attendance_by_id]
    if not ordered:
        raise PrintNodeError("No name tags were found to print.")

    pdf_bytes = build_label_pdf(ordered)
    payload = {
        "printerId": printer_id,
        "title": f"Welcome System Nametags {timezone.localtime():%Y-%m-%d %H:%M:%S}",
        "contentType": "pdf_base64",
        "content": base64.b64encode(pdf_bytes).decode("ascii"),
        "source": f"Welcome System kiosk {kiosk_id}",
        "expireAfter": 600,
    }
    return submit_printnode_job(api_key, payload)


def submit_test_print_job(*, kiosk_id: str) -> int:
    api_key = (get_setting("printnode_api_key", "") or "").strip()
    if not api_key:
        raise PrintNodeError("PrintNode API key is not configured.")

    printer_id = get_kiosk_printer_id(kiosk_id)
    pdf_bytes = build_test_label_pdf(kiosk_id)
    payload = {
        "printerId": printer_id,
        "title": f"Welcome System Test Label {timezone.localtime():%Y-%m-%d %H:%M:%S}",
        "contentType": "pdf_base64",
        "content": base64.b64encode(pdf_bytes).decode("ascii"),
        "source": f"Welcome System kiosk {kiosk_id}",
        "expireAfter": 600,
    }
    return submit_printnode_job(api_key, payload)


def submit_printnode_job(api_key: str, payload: dict) -> int:
    body = json.dumps(payload).encode("utf-8")
    auth = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        PRINTNODE_API_URL,
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response_body = response.read().decode("utf-8").strip()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise PrintNodeError(f"PrintNode rejected the print job: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise PrintNodeError(f"Could not reach PrintNode: {exc.reason}") from exc

    try:
        return int(json.loads(response_body))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PrintNodeError("PrintNode returned an unexpected response.") from exc


def build_label_pdf(attendances) -> bytes:
    rows = [(attendance.person.first_name, attendance.person.last_name) for attendance in attendances]
    return _build_label_pdf_from_rows(rows)


def build_test_label_pdf(kiosk_id: str) -> bytes:
    return _build_label_pdf_from_rows([("TEST", f"KIOSK {kiosk_id}")], hide_last_name_override=False)


def _build_label_pdf_from_rows(rows, *, hide_last_name_override=None) -> bytes:
    width = 2.4 * 72
    height = 1.1 * 72
    hide_last_name = (
        hide_last_name_override
        if hide_last_name_override is not None
        else _is_yes(get_setting("hide_last_name", "No"))
    )
    first_color = _hex_to_rgb(get_setting("first_name_color", "#000000"), (0, 0, 0))
    last_color = _hex_to_rgb(get_setting("last_name_color", "#000000"), (0, 0, 0))
    first_scale = _safe_percent_scale(get_setting("label_first_name_scale", "100")) / 100
    last_scale = _safe_percent_scale(get_setting("label_last_name_scale", "100")) / 100

    objects = []
    page_refs = []
    for first_name, last_name in rows:
        page_ref = len(objects) + 3
        content_ref = len(objects) + 4
        page_refs.append(page_ref)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:.2f} {height:.2f}] "
            f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> "
            f"/F2 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
            f"/Contents {content_ref} 0 R >>"
        )
        stream = _label_stream(
            first_name,
            last_name,
            width,
            height,
            hide_last_name,
            first_color,
            last_color,
            first_scale,
            last_scale,
        )
        objects.append(f"<< /Length {len(stream.encode('utf-8'))} >>\nstream\n{stream}\nendstream")

    kids = " ".join(f"{ref} 0 R" for ref in page_refs)
    pdf_objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_refs)} >>",
        *objects,
    ]
    return _write_pdf(pdf_objects)


def _label_stream(
    first_name,
    last_name,
    width,
    height,
    hide_last_name,
    first_color,
    last_color,
    first_scale,
    last_scale,
):
    first_text = (first_name or "").upper()
    last_text = (last_name or "").upper()
    first_size = _name_size(first_text, 30 * first_scale, 24 * first_scale, 20 * first_scale)
    last_size = _name_size(last_text, 13 * last_scale, 11 * last_scale, 9 * last_scale)
    if hide_last_name:
        first_y = (height - first_size) / 2 + 2
        return _text_line(first_text, first_size, first_y, width, first_size, first_color, "F1")

    first_y = height * 0.52
    last_y = height * 0.28
    return "\n".join(
        [
            _text_line(first_text, first_size, first_y, width, first_size, first_color, "F1"),
            _text_line(last_text, last_size, last_y, width, last_size, last_color, "F2"),
        ]
    )


def _text_line(text, font_size, y, page_width, max_font_size, color, font_name):
    estimated_width = len(text) * font_size * 0.56
    x = max((page_width - estimated_width) / 2, 6)
    red, green, blue = color
    return (
        "BT\n"
        f"{red:.3f} {green:.3f} {blue:.3f} rg\n"
        f"/{font_name} {max_font_size:.2f} Tf\n"
        f"1 0 0 1 {x:.2f} {y:.2f} Tm\n"
        f"({_pdf_escape(text)}) Tj\n"
        "ET"
    )


def _write_pdf(objects) -> bytes:
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n{obj}\nendobj\n".encode("utf-8"))
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _name_size(text: str, default: float, small: float, tiny: float) -> float:
    if len(text) > 14:
        return tiny
    if len(text) > 10:
        return small
    return default


def _safe_percent_scale(value: str, default: int = 100) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(50, min(parsed, 200))


def _is_yes(value: str) -> bool:
    return str(value or "").strip().lower() in {"yes", "true", "1"}


def _hex_to_rgb(value: str, default):
    if not value or not re.match(r"^#[0-9a-fA-F]{6}$", value):
        return default
    return tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))
