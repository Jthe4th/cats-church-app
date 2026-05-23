import base64
import json
from pathlib import Path
import re
import socket
import urllib.error
import urllib.request

from brother_ql.conversion import convert
from brother_ql.raster import BrotherQLRaster
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from .models import Attendance
from .settings_store import get_setting


PRINT_MODE_CONNECTED = "Connected Printer"
PRINT_MODE_PRINTNODE = "PrintNode Printer"
PRINT_MODE_SERVER = "Server Printer"
PRINTNODE_API_URL = "https://api.printnode.com/printjobs"
PRINTNODE_NOOP_URL = "https://api.printnode.com/noop"
BROTHER_MODEL = "QL-820NWB"
BROTHER_RED_LABEL = "62red"
LABEL_DPI = 300
LABEL_WIDTH_PX = 696
LABEL_HEIGHT_PX = 330


class PrintNodeError(Exception):
    """Raised when a PrintNode job cannot be submitted."""


class ServerPrinterError(Exception):
    """Raised when a server-side network printer job cannot be submitted."""


def is_printnode_mode() -> bool:
    return get_setting("print_mode", PRINT_MODE_CONNECTED).strip() == PRINT_MODE_PRINTNODE


def is_server_printer_mode() -> bool:
    return get_setting("print_mode", PRINT_MODE_CONNECTED).strip() == PRINT_MODE_SERVER


def is_managed_printer_mode() -> bool:
    return get_setting("print_mode", PRINT_MODE_CONNECTED).strip() in {PRINT_MODE_PRINTNODE, PRINT_MODE_SERVER}


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


def get_kiosk_server_printer(kiosk_id: str) -> tuple[str, int]:
    kiosk_id = (kiosk_id or "").strip()
    if not kiosk_id:
        raise ServerPrinterError("Missing kiosk id. Open the kiosk with ?kiosk=your-kiosk-name.")

    raw_map = get_setting("server_printer_map", "{}") or "{}"
    try:
        printer_map = json.loads(raw_map)
    except json.JSONDecodeError as exc:
        raise ServerPrinterError("Server printer map is not valid JSON.") from exc

    if not isinstance(printer_map, dict):
        raise ServerPrinterError("Server printer map must be a JSON object.")

    printer_config = printer_map.get(kiosk_id)
    if not printer_config:
        raise ServerPrinterError(f'No server printer is configured for kiosk "{kiosk_id}".')
    return _parse_server_printer_config(printer_config, kiosk_id)


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

    raw_bytes = build_label_raw(ordered)
    payload = {
        "printerId": printer_id,
        "title": f"Welcome System Nametags {timezone.localtime():%Y-%m-%d %H:%M:%S}",
        "contentType": "raw_base64",
        "content": base64.b64encode(raw_bytes).decode("ascii"),
        "source": f"Welcome System kiosk {kiosk_id}",
        "expireAfter": 600,
    }
    return submit_printnode_job(api_key, payload)


def submit_server_attendance_print_job(attendance_ids, *, kiosk_id: str, user=None) -> str:
    host, port = get_kiosk_server_printer(kiosk_id)
    attendances = list(
        Attendance.objects.filter(id__in=attendance_ids)
        .select_related("person", "service")
        .order_by("person__last_name", "person__first_name")
    )
    attendance_by_id = {attendance.id: attendance for attendance in attendances}
    ordered = [attendance_by_id[attendance_id] for attendance_id in attendance_ids if attendance_id in attendance_by_id]
    if not ordered:
        raise ServerPrinterError("No name tags were found to print.")

    _send_raw_to_server_printer(host, port, build_label_raw(ordered))
    return f"{host}:{port}"


def submit_test_print_job(*, kiosk_id: str) -> int:
    api_key = (get_setting("printnode_api_key", "") or "").strip()
    if not api_key:
        raise PrintNodeError("PrintNode API key is not configured.")

    printer_id = get_kiosk_printer_id(kiosk_id)
    raw_bytes = build_test_label_raw(kiosk_id)
    payload = {
        "printerId": printer_id,
        "title": f"Welcome System Test Label {timezone.localtime():%Y-%m-%d %H:%M:%S}",
        "contentType": "raw_base64",
        "content": base64.b64encode(raw_bytes).decode("ascii"),
        "source": f"Welcome System kiosk {kiosk_id}",
        "expireAfter": 600,
    }
    return submit_printnode_job(api_key, payload)


def submit_server_test_print_job(*, kiosk_id: str) -> str:
    host, port = get_kiosk_server_printer(kiosk_id)
    _send_raw_to_server_printer(host, port, build_test_label_raw(kiosk_id))
    return f"{host}:{port}"


def _send_raw_to_server_printer(host: str, port: int, raw_bytes: bytes) -> None:
    timeout = _safe_int(get_setting("server_printer_timeout_seconds", "10"), 10, minimum=1, maximum=60)
    try:
        with socket.create_connection((host, port), timeout=timeout) as printer_socket:
            printer_socket.sendall(raw_bytes)
    except OSError as exc:
        raise ServerPrinterError(f"Could not reach server printer at {host}:{port}: {exc}") from exc


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


def verify_printnode_api_key(api_key: str | None = None) -> tuple[bool, str]:
    api_key = (api_key if api_key is not None else get_setting("printnode_api_key", "") or "").strip()
    if not api_key:
        return False, "PrintNode API key is blank."

    auth = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        PRINTNODE_NOOP_URL,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(detail)
            message = payload.get("message") or payload.get("code") or detail
        except json.JSONDecodeError:
            message = detail or exc.reason
        return False, f"PrintNode rejected the API key: {message}"
    except urllib.error.URLError as exc:
        return False, f"Could not reach PrintNode: {exc.reason}"
    return True, "PrintNode API key verified."


def build_label_pdf(attendances) -> bytes:
    rows = [(attendance.person.first_name, attendance.person.last_name) for attendance in attendances]
    return _build_label_pdf_from_rows(rows)


def build_test_label_pdf(kiosk_id: str) -> bytes:
    return _build_label_pdf_from_rows([("TEST", f"KIOSK {kiosk_id}")], hide_last_name_override=False, draw_border=True)


def build_label_raw(attendances) -> bytes:
    rows = [(attendance.person.first_name, attendance.person.last_name) for attendance in attendances]
    return _build_label_raw_from_rows(rows)


def build_test_label_raw(kiosk_id: str) -> bytes:
    return _build_label_raw_from_rows([("TEST", f"KIOSK {kiosk_id}")])


def _build_label_raw_from_rows(rows, *, draw_border=False) -> bytes:
    qlr = BrotherQLRaster(BROTHER_MODEL)
    images = [_label_image(first_name, last_name, draw_border=draw_border) for first_name, last_name in rows]
    convert(
        qlr,
        images,
        BROTHER_RED_LABEL,
        cut=True,
        dither=False,
        compress=True,
        red=True,
        rotate=0,
        threshold=70,
    )
    return qlr.data


def _label_image(first_name, last_name, *, draw_border=False):
    first_text = (first_name or "").upper()
    last_text = (last_name or "").upper()
    image = Image.new("RGB", (LABEL_WIDTH_PX, LABEL_HEIGHT_PX), "white")
    draw = ImageDraw.Draw(image)
    margin = int(_safe_inches(get_setting("printnode_label_margin_in", "0.1"), 0.1) * LABEL_DPI)
    first_color = _hex_to_255_rgb(get_setting("first_name_color", "#000000"), (0, 0, 0))
    last_color = _hex_to_255_rgb(get_setting("last_name_color", "#000000"), (0, 0, 0))
    first_scale = _safe_percent_scale(get_setting("label_first_name_scale", "100")) / 100
    last_scale = _safe_percent_scale(get_setting("label_last_name_scale", "100")) / 100
    hide_last_name = _is_yes(get_setting("hide_last_name", "No"))

    if draw_border:
        draw.rectangle(
            (margin // 2, margin // 2, LABEL_WIDTH_PX - (margin // 2), LABEL_HEIGHT_PX - (margin // 2)),
            outline=(0, 0, 0),
            width=3,
        )

    first_font = _fit_font(first_text, int(112 * first_scale), LABEL_WIDTH_PX - margin * 2, bold=True)
    if hide_last_name:
        _center_text(draw, first_text, first_font, first_color, LABEL_WIDTH_PX / 2, LABEL_HEIGHT_PX / 2)
        return image

    last_font = _fit_font(last_text, int(52 * last_scale), LABEL_WIDTH_PX - margin * 2, bold=False)
    _center_text(draw, first_text, first_font, first_color, LABEL_WIDTH_PX / 2, LABEL_HEIGHT_PX * 0.42)
    _center_text(draw, last_text, last_font, last_color, LABEL_WIDTH_PX / 2, LABEL_HEIGHT_PX * 0.68)
    return image


def _center_text(draw, text, font, fill, center_x, center_y):
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    draw.text((center_x - width / 2, center_y - height / 2 - bbox[1]), text, font=font, fill=fill)


def _fit_font(text, starting_size, max_width, *, bold):
    size = max(starting_size, 12)
    while size > 12:
        font = _load_font(size, bold=bold)
        bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 4
    return _load_font(size, bold=bold)


def _load_font(size, *, bold):
    font_names = (
        ("Arial Bold.ttf", "Arial.ttf"),
        ("Helvetica.ttc", "Helvetica.ttc"),
        ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"),
    )
    search_dirs = (
        Path("/System/Library/Fonts/Supplemental"),
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
    )
    for bold_name, regular_name in font_names:
        name = bold_name if bold else regular_name
        for directory in search_dirs:
            path = directory / name
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    continue
    return ImageFont.load_default()


def _build_label_pdf_from_rows(rows, *, hide_last_name_override=None, draw_border=False) -> bytes:
    width = _safe_inches(get_setting("printnode_label_width_in", "2.440"), 2.440) * 72
    height = _safe_inches(get_setting("printnode_label_height_in", "1.1"), 1.1) * 72
    margin = _safe_inches(get_setting("printnode_label_margin_in", "0.1"), 0.1) * 72
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
            margin,
            draw_border,
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
    margin,
    draw_border,
):
    first_text = (first_name or "").upper()
    last_text = (last_name or "").upper()
    first_size = _name_size(first_text, 30 * first_scale, 24 * first_scale, 20 * first_scale)
    last_size = _name_size(last_text, 13 * last_scale, 11 * last_scale, 9 * last_scale)
    if hide_last_name:
        first_y = (height - first_size) / 2 + 2
        stream_parts = [
            _red_accent_stream(width, height, margin),
            _text_line(first_text, first_size, first_y, width, first_size, first_color, "F1", margin),
        ]
        if draw_border:
            stream_parts.insert(0, _border_stream(width, height, margin))
        return "\n".join(stream_parts)

    first_y = height * 0.52
    last_y = height * 0.28
    stream_parts = [
        _red_accent_stream(width, height, margin),
        _text_line(first_text, first_size, first_y, width, first_size, first_color, "F1", margin),
        _text_line(last_text, last_size, last_y, width, last_size, last_color, "F2", margin),
    ]
    if draw_border:
        stream_parts.insert(0, _border_stream(width, height, margin))
    return "\n".join(stream_parts)


def _text_line(text, font_size, y, page_width, max_font_size, color, font_name, margin):
    available_width = max(page_width - (margin * 2), 24)
    while len(text) * font_size * 0.56 > available_width and font_size > 7:
        font_size -= 1
        max_font_size = font_size
    estimated_width = len(text) * font_size * 0.56
    x = max((page_width - estimated_width) / 2, margin)
    red, green, blue = color
    return (
        "BT\n"
        f"{red:.3f} {green:.3f} {blue:.3f} rg\n"
        f"/{font_name} {max_font_size:.2f} Tf\n"
        f"1 0 0 1 {x:.2f} {y:.2f} Tm\n"
        f"({_pdf_escape(text)}) Tj\n"
        "ET"
    )


def _border_stream(width, height, margin):
    return (
        "0.000 0.000 0.000 RG\n"
        "0.75 w\n"
        f"{margin:.2f} {margin:.2f} {max(width - (margin * 2), 1):.2f} {max(height - (margin * 2), 1):.2f} re S"
    )


def _red_accent_stream(width, height, margin):
    accent_width = max(width - (margin * 4), 1)
    y = max(margin * 1.5, 4)
    return (
        "1.000 0.000 0.000 RG\n"
        "2.00 w\n"
        f"{margin * 2:.2f} {y:.2f} m {margin * 2 + accent_width:.2f} {y:.2f} l S"
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


def _safe_inches(value: str, default: float) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, 10)


def _safe_int(value: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _parse_server_printer_config(printer_config, kiosk_id: str) -> tuple[str, int]:
    if isinstance(printer_config, dict):
        host = str(printer_config.get("host", "")).strip()
        port_value = printer_config.get("port", 9100)
    else:
        raw_value = str(printer_config or "").strip()
        if ":" in raw_value:
            host, port_value = raw_value.rsplit(":", 1)
            host = host.strip()
        else:
            host, port_value = raw_value, 9100
    if not host:
        raise ServerPrinterError(f'Server printer host for kiosk "{kiosk_id}" cannot be blank.')
    try:
        port = int(str(port_value).strip())
    except (TypeError, ValueError) as exc:
        raise ServerPrinterError(f'Server printer port for kiosk "{kiosk_id}" must be a number.') from exc
    if port < 1 or port > 65535:
        raise ServerPrinterError(f'Server printer port for kiosk "{kiosk_id}" must be between 1 and 65535.')
    return host, port


def _is_yes(value: str) -> bool:
    return str(value or "").strip().lower() in {"yes", "true", "1"}


def _hex_to_rgb(value: str, default):
    if not value or not re.match(r"^#[0-9a-fA-F]{6}$", value):
        return default
    return tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))


def _hex_to_255_rgb(value: str, default):
    if not value or not re.match(r"^#[0-9a-fA-F]{6}$", value):
        return default
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
