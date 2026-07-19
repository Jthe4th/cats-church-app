import base64
import html
import json
import logging
import platform
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import warnings

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
BROTHER_DEFAULT_LABEL = "62red"
BROTHER_LABEL_MEDIA_CHOICES = {"62", "62red"}
PRINTER_PROFILE_BACKENDS = {"printnode", "server"}
LABEL_DPI = 300
LABEL_WIDTH_PX = 696
LABEL_HEIGHT_PX = 330
BROTHER_QL_LOGGER = "brother_ql.devicedependent"
FONT_FILE_CANDIDATES = {
    "Arial": (("Arial Bold.ttf", "Arial.ttf"), ("ArialHB.ttc", "Arial.ttf")),
    "Helvetica": (("Helvetica.ttc", "Helvetica.ttc"), ("HelveticaNeue.ttc", "HelveticaNeue.ttc")),
    "Georgia": (("Georgia Bold.ttf", "Georgia.ttf"),),
    "Times New Roman": (("Times New Roman Bold.ttf", "Times New Roman.ttf"), ("Times.ttc", "Times.ttc")),
    "Trebuchet MS": (("Trebuchet MS Bold.ttf", "Trebuchet MS.ttf"),),
    "Verdana": (("Verdana Bold.ttf", "Verdana.ttf"),),
}


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
    printer_id, _profile = _get_kiosk_printnode_target(kiosk_id)
    return printer_id


def _get_kiosk_printnode_target(kiosk_id: str) -> tuple[int, dict | None]:
    kiosk_id = _normalize_kiosk_id(kiosk_id, PrintNodeError)
    profile = _get_kiosk_printer_profile(kiosk_id, "printnode", PrintNodeError)
    if profile:
        printer_id = str(profile.get("printer_id") or profile.get("printnode_printer_id") or "").strip()
        if not printer_id:
            raise PrintNodeError(f'Printer profile "{profile["name"]}" must include a PrintNode printer_id.')
        if not printer_id.isdigit():
            raise PrintNodeError(f'PrintNode printer id in profile "{profile["name"]}" must be a number.')
        return int(printer_id), profile

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
    return int(printer_id), None


def get_kiosk_server_printer(kiosk_id: str) -> dict:
    target, _profile = _get_kiosk_server_printer_target(kiosk_id)
    return target


def _get_kiosk_server_printer_target(kiosk_id: str) -> tuple[dict, dict | None]:
    kiosk_id = _normalize_kiosk_id(kiosk_id, ServerPrinterError)
    profile = _get_kiosk_printer_profile(kiosk_id, "server", ServerPrinterError)
    if profile:
        printer_config = _profile_server_printer_config(profile)
        if not printer_config:
            raise ServerPrinterError(f'Printer profile "{profile["name"]}" must include a server target, queue, or host.')
        return _parse_server_printer_config(printer_config, kiosk_id), profile

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
    return _parse_server_printer_config(printer_config, kiosk_id), None


def submit_attendance_print_job(attendance_ids, *, kiosk_id: str, user=None) -> int:
    api_key = (get_setting("printnode_api_key", "") or "").strip()
    if not api_key:
        raise PrintNodeError("PrintNode API key is not configured.")

    printer_id, profile = _get_kiosk_printnode_target(kiosk_id)
    attendances = list(
        Attendance.objects.filter(id__in=attendance_ids)
        .select_related("person", "service")
        .order_by("person__last_name", "person__first_name")
    )
    attendance_by_id = {attendance.id: attendance for attendance in attendances}
    ordered = [attendance_by_id[attendance_id] for attendance_id in attendance_ids if attendance_id in attendance_by_id]
    if not ordered:
        raise PrintNodeError("No name tags were found to print.")

    raw_bytes = build_label_raw(ordered, profile=profile)
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
    target, profile = _get_kiosk_server_printer_target(kiosk_id)
    attendances = list(
        Attendance.objects.filter(id__in=attendance_ids)
        .select_related("person", "service")
        .order_by("person__last_name", "person__first_name")
    )
    attendance_by_id = {attendance.id: attendance for attendance in attendances}
    ordered = [attendance_by_id[attendance_id] for attendance_id in attendance_ids if attendance_id in attendance_by_id]
    if not ordered:
        raise ServerPrinterError("No name tags were found to print.")

    return _send_to_server_printer_target(
        target,
        raw_bytes=build_label_raw(ordered, profile=profile),
        pdf_bytes=build_label_pdf(ordered, profile=profile),
        images=build_label_images(ordered, profile=profile),
    )


def submit_test_print_job(*, kiosk_id: str) -> int:
    api_key = (get_setting("printnode_api_key", "") or "").strip()
    if not api_key:
        raise PrintNodeError("PrintNode API key is not configured.")

    printer_id, profile = _get_kiosk_printnode_target(kiosk_id)
    raw_bytes = build_test_label_raw(kiosk_id, profile=profile)
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
    target, profile = _get_kiosk_server_printer_target(kiosk_id)
    return _send_to_server_printer_target(
        target,
        raw_bytes=build_test_label_raw(kiosk_id, profile=profile),
        pdf_bytes=build_test_label_pdf(kiosk_id, profile=profile),
        images=build_test_label_images(kiosk_id, profile=profile),
    )


def _send_to_server_printer_target(target: dict, *, raw_bytes: bytes, pdf_bytes: bytes, images=None) -> str:
    if target["kind"] == "queue":
        if platform.system() == "Windows":
            return _send_images_to_windows_print_queue(target["queue"], images or [])
        return _send_pdf_to_print_queue(target["queue"], pdf_bytes)
    host = target["host"]
    port = target["port"]
    _send_raw_to_server_printer(host, port, raw_bytes)
    return f"raw:{host}:{port}"


def _send_images_to_windows_print_queue(queue_name: str, images) -> str:
    if not images:
        raise ServerPrinterError("No label images were available for the Windows print queue.")
    try:
        import win32con
        import win32print
        import win32ui
        from PIL import ImageWin
    except ImportError as exc:
        raise ServerPrinterError(
            "Windows printer queues require pywin32. Run pip install -r requirements.txt, then restart the app."
        ) from exc

    printer_dc = None
    try:
        printer_dc = win32ui.CreateDC()
        printer_dc.CreatePrinterDC(queue_name)
        printable_width = printer_dc.GetDeviceCaps(win32con.HORZRES)
        printable_height = printer_dc.GetDeviceCaps(win32con.VERTRES)
        printer_dc.StartDoc(f"Welcome System Nametags {timezone.localtime():%Y-%m-%d %H:%M:%S}")
        for image in images:
            printer_dc.StartPage()
            rendered = image.convert("RGB")
            scale = min(printable_width / rendered.width, printable_height / rendered.height)
            width = max(1, int(rendered.width * scale))
            height = max(1, int(rendered.height * scale))
            left = max(0, int((printable_width - width) / 2))
            top = max(0, int((printable_height - height) / 2))
            ImageWin.Dib(rendered).draw(printer_dc.GetHandleOutput(), (left, top, left + width, top + height))
            printer_dc.EndPage()
        printer_dc.EndDoc()
    except Exception as exc:
        raise ServerPrinterError(f'Windows print queue "{queue_name}" rejected the job: {exc}') from exc
    finally:
        if printer_dc:
            printer_dc.DeleteDC()
    return f"queue:{queue_name}"


def _send_pdf_to_print_queue(queue_name: str, pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(prefix="welcome-label-", suffix=".pdf") as label_file:
        label_file.write(pdf_bytes)
        label_file.flush()
        try:
            result = subprocess.run(
                ["lp", "-d", queue_name, "-t", f"Welcome System Nametags {timezone.localtime():%Y-%m-%d %H:%M:%S}", label_file.name],
                check=True,
                capture_output=True,
                text=True,
                timeout=_safe_int(get_setting("server_printer_timeout_seconds", "10"), 10, minimum=1, maximum=60),
            )
        except FileNotFoundError as exc:
            raise ServerPrinterError("The lp command is not available on this server computer.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ServerPrinterError(f'Print queue "{queue_name}" did not accept the job before the timeout.') from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise ServerPrinterError(f'Print queue "{queue_name}" rejected the job: {detail or exc.returncode}') from exc
    return _parse_lp_job_id(result.stdout) or f"queue:{queue_name}"


def _send_raw_to_server_printer(host: str, port: int, raw_bytes: bytes) -> None:
    timeout = _safe_int(get_setting("server_printer_timeout_seconds", "10"), 10, minimum=1, maximum=60)
    _validate_raw_brother_status(host, timeout=min(timeout, 5))
    try:
        with socket.create_connection((host, port), timeout=timeout) as printer_socket:
            printer_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            printer_socket.sendall(raw_bytes)
            try:
                printer_socket.shutdown(socket.SHUT_WR)
            except OSError:
                pass
    except OSError as exc:
        raise ServerPrinterError(f"Could not reach server printer at {host}:{port}: {exc}") from exc
    time.sleep(0.75)
    _validate_raw_brother_status(host, timeout=min(timeout, 5), after_send=True)


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


def build_label_pdf(attendances, *, profile=None) -> bytes:
    rows = [(attendance.person.first_name, attendance.person.last_name) for attendance in attendances]
    return _build_label_pdf_from_rows(rows, profile=profile)


def build_test_label_pdf(kiosk_id: str, *, profile=None) -> bytes:
    return _build_label_pdf_from_rows([("TEST", f"KIOSK {kiosk_id}")], hide_last_name_override=False, profile=profile)


def build_label_raw(attendances, *, profile=None) -> bytes:
    rows = [(attendance.person.first_name, attendance.person.last_name) for attendance in attendances]
    return _build_label_raw_from_rows(rows, profile=profile)


def build_test_label_raw(kiosk_id: str, *, profile=None) -> bytes:
    return _build_label_raw_from_rows([("TEST", f"KIOSK {kiosk_id}")], profile=profile)


def build_label_images(attendances, *, profile=None):
    rows = [(attendance.person.first_name, attendance.person.last_name) for attendance in attendances]
    return _build_label_images_from_rows(rows, profile=profile)


def build_test_label_images(kiosk_id: str, *, profile=None):
    return _build_label_images_from_rows([("TEST", f"KIOSK {kiosk_id}")], profile=profile)


def _build_label_images_from_rows(rows, *, draw_border=False, profile=None):
    return [
        _label_image(first_name, last_name, draw_border=draw_border, profile=profile)
        for first_name, last_name in rows
    ]


def _build_label_raw_from_rows(rows, *, draw_border=False, profile=None) -> bytes:
    convert, BrotherQLRaster = _load_brother_ql()
    qlr = BrotherQLRaster(BROTHER_MODEL)
    images = _build_label_images_from_rows(rows, draw_border=draw_border, profile=profile)
    brother_label_media = _brother_label_media(profile=profile)
    if brother_label_media == "62red":
        images = [_normalize_brother_label_colors(image) for image in images]
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Image\.Image\.getdata is deprecated.*",
            category=DeprecationWarning,
        )
        convert(
            qlr,
            images,
            brother_label_media,
            cut=True,
            dither=False,
            compress=True,
            red=brother_label_media == "62red",
            rotate=0,
            threshold=70,
        )
    return qlr.data


def _load_brother_ql():
    logging.getLogger(BROTHER_QL_LOGGER).setLevel(logging.ERROR)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The 'warn' method is deprecated, use 'warning' instead",
            category=DeprecationWarning,
        )
        from brother_ql.conversion import convert
        from brother_ql.raster import BrotherQLRaster

    return convert, BrotherQLRaster


def _label_image(first_name, last_name, *, draw_border=False, profile=None):
    first_text = (first_name or "").upper()
    last_text = (last_name or "").upper()
    image = Image.new("RGB", (LABEL_WIDTH_PX, LABEL_HEIGHT_PX), "white")
    draw = ImageDraw.Draw(image)
    margin = int(_safe_inches(_profile_setting(profile, "printnode_label_margin_in", "0.1"), 0.1) * LABEL_DPI)
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


def _normalize_brother_label_colors(image):
    normalized = Image.new("RGB", image.size, "white")
    pixels = []
    for red, green, blue in image.convert("RGB").getdata():
        luma = (red * 0.299) + (green * 0.587) + (blue * 0.114)
        is_red = red >= 120 and red > green * 1.35 and red > blue * 1.35
        if is_red and luma < 245:
            pixels.append((255, 0, 0))
        elif luma < 220:
            pixels.append((0, 0, 0))
        else:
            pixels.append((255, 255, 255))
    normalized.putdata(pixels)
    return normalized


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
    font_names = _configured_font_file_candidates()
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


def _configured_font_file_candidates():
    configured_font = (get_setting("label_font", "Arial") or "Arial").strip()
    selected = FONT_FILE_CANDIDATES.get(configured_font, ())
    fallback = (
        ("Arial Bold.ttf", "Arial.ttf"),
        ("Helvetica.ttc", "Helvetica.ttc"),
        ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"),
    )
    return (*selected, *tuple(pair for pair in fallback if pair not in selected))


def _build_label_pdf_from_rows(rows, *, hide_last_name_override=None, draw_border=False, profile=None) -> bytes:
    width = _safe_inches(_profile_setting(profile, "printnode_label_width_in", "2.440"), 2.440) * 72
    height = _safe_inches(_profile_setting(profile, "printnode_label_height_in", "1.1"), 1.1) * 72
    margin = _safe_inches(_profile_setting(profile, "printnode_label_margin_in", "0.1"), 0.1) * 72
    hide_last_name = (
        hide_last_name_override
        if hide_last_name_override is not None
        else _is_yes(get_setting("hide_last_name", "No"))
    )
    first_color = _hex_to_rgb(get_setting("first_name_color", "#000000"), (0, 0, 0))
    last_color = _hex_to_rgb(get_setting("last_name_color", "#000000"), (0, 0, 0))
    first_scale = _safe_percent_scale(get_setting("label_first_name_scale", "100")) / 100
    last_scale = _safe_percent_scale(get_setting("label_last_name_scale", "100")) / 100
    pdf_bold_font, pdf_regular_font = _configured_pdf_font_names()

    objects = []
    page_refs = []
    for first_name, last_name in rows:
        page_ref = len(objects) + 3
        content_ref = len(objects) + 4
        page_refs.append(page_ref)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:.2f} {height:.2f}] "
            f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /{pdf_bold_font} >> "
            f"/F2 << /Type /Font /Subtype /Type1 /BaseFont /{pdf_regular_font} >> >> >> "
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
            _text_line(first_text, first_size, first_y, width, first_size, first_color, "F1", margin),
        ]
        if draw_border:
            stream_parts.insert(0, _border_stream(width, height, margin))
        return "\n".join(stream_parts)

    first_y = height * 0.52
    last_y = height * 0.28
    stream_parts = [
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


def _normalize_kiosk_id(kiosk_id: str, error_class):
    kiosk_id = (kiosk_id or "").strip()
    if not kiosk_id:
        raise error_class("Missing kiosk id. Open the kiosk with ?kiosk=your-kiosk-name.")
    return kiosk_id


def _get_kiosk_printer_profile(kiosk_id: str, expected_backend: str, error_class) -> dict | None:
    profile_name = _get_kiosk_printer_profile_name(kiosk_id, error_class)
    if not profile_name:
        return None

    raw_profiles = get_setting("printer_profiles", "{}") or "{}"
    try:
        profiles = json.loads(raw_profiles)
    except json.JSONDecodeError as exc:
        raise error_class("Printer profiles setting is not valid JSON.") from exc
    if not isinstance(profiles, dict):
        raise error_class("Printer profiles setting must be a JSON object.")

    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise error_class(f'Printer profile "{profile_name}" is not configured.')

    backend = str(profile.get("backend", expected_backend)).strip().lower()
    if backend and backend not in PRINTER_PROFILE_BACKENDS:
        raise error_class(f'Printer profile "{profile_name}" has an unsupported backend "{backend}".')
    if backend != expected_backend:
        raise error_class(f'Printer profile "{profile_name}" is for {backend}, not {expected_backend}.')
    return {"name": profile_name, **profile}


def _get_kiosk_printer_profile_name(kiosk_id: str, error_class) -> str:
    raw_map = get_setting("kiosk_printer_profile_map", "{}") or "{}"
    try:
        profile_map = json.loads(raw_map)
    except json.JSONDecodeError as exc:
        raise error_class("Kiosk printer profile map is not valid JSON.") from exc
    if not isinstance(profile_map, dict):
        raise error_class("Kiosk printer profile map must be a JSON object.")
    return str(profile_map.get(kiosk_id, "")).strip()


def _profile_server_printer_config(profile: dict):
    if "target" in profile:
        return profile.get("target")
    if profile.get("queue"):
        return {"queue": profile.get("queue")}
    if profile.get("host"):
        return {"host": profile.get("host"), "port": profile.get("port", 9100)}
    return None


def _profile_setting(profile: dict | None, key: str, default: str) -> str:
    aliases = {
        "printnode_label_width_in": ("printnode_label_width_in", "label_width_in", "width_in"),
        "printnode_label_height_in": ("printnode_label_height_in", "label_height_in", "height_in"),
        "printnode_label_margin_in": ("printnode_label_margin_in", "label_margin_in", "margin_in"),
        "brother_label_media": ("brother_label_media", "media"),
    }
    for profile_key in aliases.get(key, (key,)):
        if profile and profile.get(profile_key) not in (None, ""):
            return str(profile.get(profile_key))
    return get_setting(key, default)


def _parse_server_printer_config(printer_config, kiosk_id: str) -> dict:
    if isinstance(printer_config, dict):
        queue_name = str(printer_config.get("queue", "")).strip()
        if queue_name:
            return {"kind": "queue", "queue": queue_name}
        host = str(printer_config.get("host", "")).strip()
        port_value = printer_config.get("port", 9100)
    else:
        raw_value = str(printer_config or "").strip()
        if raw_value.startswith("queue:"):
            queue_name = raw_value.removeprefix("queue:").strip()
            if not queue_name:
                raise ServerPrinterError(f'Server printer queue for kiosk "{kiosk_id}" cannot be blank.')
            return {"kind": "queue", "queue": queue_name}
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
    return {"kind": "raw", "host": host, "port": port}


def _parse_lp_job_id(output: str) -> str:
    match = re.search(r"request id is ([^\s]+)", output or "")
    if not match:
        return ""
    return f"queue:{match.group(1)}"


def _configured_pdf_font_names() -> tuple[str, str]:
    configured_font = (get_setting("label_font", "Arial") or "Arial").strip()
    if configured_font in {"Georgia", "Times New Roman", "Merriweather", "Playfair Display", "Noto Serif"}:
        return "Times-Bold", "Times-Roman"
    return "Helvetica-Bold", "Helvetica"


def _validate_raw_brother_status(host: str, *, timeout: int, after_send: bool = False) -> None:
    status = _fetch_brother_web_status(host, timeout=timeout)
    if not status:
        return
    device_status = status.get("device_status", "").lower()
    media_status = status.get("media_status", "").lower()
    accepted_statuses = {"ready", "printing"} if after_send else {"ready"}
    if device_status and device_status not in accepted_statuses:
        prefix = "rejected the print job" if after_send else "is not ready"
        raise ServerPrinterError(
            f'Brother printer at {host} {prefix}. Current status: {status.get("device_status")}. Check the printer LCD for details.'
        )
    if media_status == "empty":
        raise ServerPrinterError(
            f'Brother printer at {host} reports empty media. Load a label roll, then try again.'
        )


def _fetch_brother_web_status(host: str, *, timeout: int) -> dict:
    request = urllib.request.Request(f"http://{host}/", headers={"User-Agent": "Welcome System"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(20000).decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError):
        return {}
    if "Brother" not in body or "QL-" not in body:
        return {}
    return {
        "emulation": _extract_brother_status_value(body, "Emulation"),
        "device_status": _extract_brother_status_value(body, "Device Status"),
        "media_status": _extract_brother_status_value(body, "Media Status"),
        "media_type": _extract_brother_status_value(body, "Media Type"),
    }


def _extract_brother_status_value(body: str, label: str) -> str:
    escaped_label = re.escape(label).replace("\\ ", r"(?:\s|&#32;)+")
    pattern = rf"<dt[^>]*>{escaped_label}</dt><dd[^>]*>(.*?)</dd>"
    match = re.search(pattern, body, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    value = re.sub(r"<[^>]+>", " ", match.group(1))
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _brother_label_media(*, profile=None) -> str:
    media = (_profile_setting(profile, "brother_label_media", BROTHER_DEFAULT_LABEL) or BROTHER_DEFAULT_LABEL).strip()
    if media not in BROTHER_LABEL_MEDIA_CHOICES:
        return BROTHER_DEFAULT_LABEL
    return media


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
