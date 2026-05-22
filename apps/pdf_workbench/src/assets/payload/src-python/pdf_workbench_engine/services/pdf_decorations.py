from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .pdf_fonts import (
    PDF_WORKBENCH_FALLBACK_FONT,
    preferred_font_file,
    text_insert_kwargs,
    text_width,
)
from .pdf_document import _import_fitz, open_fitz_document

HEADER_FOOTER_FONT_SIZE = 8.5
HEADER_FOOTER_COLOR = (0.0, 0.0, 0.0)


def _is_header_footer(kind: Any) -> bool:
    return kind in {"header", "footer", "page-number"}


def _slot_index(position: str) -> int:
    if position.endswith("-left"):
        return 0
    if position.endswith("-right"):
        return 2
    return 1


def _slot_align_name(position: str) -> str:
    if position.endswith("-left"):
        return "left"
    if position.endswith("-right"):
        return "right"
    return "center"


def _align_from_name(fitz: Any, align: Any) -> int:
    if align == "left":
        return int(getattr(fitz, "TEXT_ALIGN_LEFT", 0))
    if align == "right":
        return int(getattr(fitz, "TEXT_ALIGN_RIGHT", 2))
    return int(getattr(fitz, "TEXT_ALIGN_CENTER", 1))


def _hex_from_color(color: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(channel * 255))):02x}" for channel in color)


def _rgb_from_manifest_color(value: Any, fallback: tuple[float, float, float]) -> tuple[float, float, float]:
    return _color_from_hex(value, fallback)


def _font_family_label() -> str:
    font_file = preferred_font_file()
    if font_file:
        stem = font_file.stem.lower()
        if "biz-udgothic" in stem:
            return "BIZ UDPGothic"
        if "yugoth" in stem:
            return "Yu Gothic"
        if "meiryo" in stem:
            return "Meiryo"
    return PDF_WORKBENCH_FALLBACK_FONT


def _header_footer_slot_area(fitz: Any, page_rect: Any, position: str, font_size: float) -> Any:
    margin_x = max(18.0, min(42.0, page_rect.width * 0.06))
    margin_y = max(10.0, min(32.0, page_rect.height * 0.042))
    band_height = max(12.0, font_size + 4.0)
    available_width = max(48.0, page_rect.width - (margin_x * 2))
    slot_width = available_width / 3
    index = _slot_index(position)
    x0 = margin_x + (slot_width * index)
    x1 = margin_x + (slot_width * (index + 1))
    if position.startswith("bottom"):
        y1 = page_rect.height - margin_y
        y0 = y1 - band_height
    else:
        y0 = margin_y
        y1 = y0 + band_height
    return fitz.Rect(x0, y0, x1, y1)


def _fit_text_to_width(text: str, font_size: float, max_width: float) -> str:
    if _text_width(text, font_size) <= max_width:
        return text

    suffix = "..."
    suffix_width = _text_width(suffix, font_size)
    if suffix_width >= max_width:
        return ""

    low = 0
    high = len(text)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = f"{text[:mid]}{suffix}"
        if _text_width(candidate, font_size) <= max_width:
            low = mid
        else:
            high = mid - 1
    return f"{text[:low].rstrip()}{suffix}" if low > 0 else ""


def _color_from_hex(value: Any, fallback: tuple[float, float, float]) -> tuple[float, float, float]:
    text = str(value or "").strip()
    if text.startswith("#") and len(text) == 7:
        try:
            return tuple(int(text[index : index + 2], 16) / 255 for index in (1, 3, 5))  # type: ignore[return-value]
        except ValueError:
            return fallback
    return fallback


def _watermark_font_size(page_rect: Any, text: str) -> float:
    length = max(6, len(text))
    base = min(page_rect.width, page_rect.height) * 0.11
    return max(18, min(54, base * (12 / length)))


def _text_for(
    decoration: dict[str, Any],
    page_index: int,
    total: int,
    page_context: dict[str, Any] | None = None,
) -> str:
    text = str(decoration.get("text") or "")
    if decoration.get("kind") == "page-number":
        text = text or "{page} / {total}"
    output_page_number = page_index + 1
    output_page_total = total
    if page_context:
        if isinstance(page_context.get("outputPageNumber"), int):
            output_page_number = int(page_context["outputPageNumber"])
        if isinstance(page_context.get("outputPageTotal"), int):
            output_page_total = int(page_context["outputPageTotal"])
    return text.replace("{page}", str(output_page_number)).replace("{total}", str(output_page_total))


def _text_width(text: str, font_size: float) -> float:
    return text_width(text, font_size)


def _layout_header_footer_item(
    fitz: Any,
    page_rect: Any,
    decoration: dict[str, Any],
    text: str,
    position: str,
) -> dict[str, Any] | None:
    fitted_font_size = HEADER_FOOTER_FONT_SIZE
    slot_area = _header_footer_slot_area(fitz, page_rect, position, fitted_font_size)
    fitted_text = _fit_text_to_width(text, fitted_font_size, max(10.0, slot_area.width))
    if not fitted_text:
        return None
    text_width_pt = _text_width(fitted_text, fitted_font_size)
    return {
        "sourceDecorationId": decoration.get("id"),
        "kind": decoration.get("kind"),
        "position": position,
        "slot": _slot_align_name(position),
        "text": fitted_text,
        "rectPt": [slot_area.x0, slot_area.y0, slot_area.x1, slot_area.y1],
        "baselinePt": slot_area.y0 + fitted_font_size,
        "fontSizePt": fitted_font_size,
        "color": _hex_from_color(HEADER_FOOTER_COLOR),
        "align": _slot_align_name(position),
        "textWidthPt": text_width_pt,
        "fontFamily": _font_family_label(),
    }


def _layout_watermark_item(
    fitz: Any,
    page_rect: Any,
    decoration: dict[str, Any],
    text: str,
    position: str,
    font_size: float,
    color: tuple[float, float, float],
) -> dict[str, Any]:
    text_width_pt = _text_width(text, font_size)
    center = fitz.Point(page_rect.width / 2, page_rect.height / 2)
    point = fitz.Point(center.x - text_width_pt / 2, center.y)
    return {
        "sourceDecorationId": decoration.get("id"),
        "kind": decoration.get("kind"),
        "position": position,
        "text": text,
        "pointPt": [point.x, point.y],
        "centerPt": [center.x, center.y],
        "fontSizePt": font_size,
        "color": _hex_from_color(color),
        "align": "left",
        "textWidthPt": text_width_pt,
        "fontFamily": _font_family_label(),
        "rotationDeg": -25,
        "opacity": 1.0,
    }


def resolve_page_decoration_layout(
    page_rect: Any,
    decorations: list[dict[str, Any]],
    page_index: int,
    total: int,
    page_context: dict[str, Any] | None = None,
    output_index: int | None = None,
) -> dict[str, Any]:
    fitz = _import_fitz()
    items: list[dict[str, Any]] = []
    for decoration in decorations:
        if not _applies_to_page(decoration, page_context, output_index):
            continue
        text = _text_for(decoration, page_index, total, page_context)
        if not text:
            continue

        kind = decoration.get("kind")
        position = "center" if kind == "watermark" else str(decoration.get("position") or "bottom-right")
        if _is_header_footer(kind):
            item = _layout_header_footer_item(fitz, page_rect, decoration, text, position)
            if item is not None:
                items.append(item)
            continue

        if kind == "watermark":
            font_size = _watermark_font_size(page_rect, text)
            color = _color_from_hex(decoration.get("color"), (0.84, 0.42, 0.42))
            items.append(_layout_watermark_item(fitz, page_rect, decoration, text, position, font_size, color))

    return {
        "pageWidthPt": float(page_rect.width),
        "pageHeightPt": float(page_rect.height),
        "fontFamily": _font_family_label(),
        "items": items,
    }


def _draw_layout_item(page: Any, item: dict[str, Any]) -> None:
    fitz = _import_fitz()
    text = str(item.get("text") or "")
    if not text:
        return
    kind = item.get("kind")
    font_size = float(item.get("fontSizePt") or HEADER_FOOTER_FONT_SIZE)
    color = _rgb_from_manifest_color(item.get("color"), HEADER_FOOTER_COLOR)

    if kind == "watermark":
        point_values = item.get("pointPt")
        center_values = item.get("centerPt")
        if not isinstance(point_values, list) or len(point_values) != 2:
            return
        if not isinstance(center_values, list) or len(center_values) != 2:
            return
        point = fitz.Point(float(point_values[0]), float(point_values[1]))
        center = fitz.Point(float(center_values[0]), float(center_values[1]))
        matrix = fitz.Matrix(1, 1).prerotate(float(item.get("rotationDeg") or -25))
        _insert_text(page, point, text, font_size, color, morph=(center, matrix))
        return

    if _is_header_footer(kind):
        rect_values = item.get("rectPt")
        if not isinstance(rect_values, list) or len(rect_values) != 4:
            return
        rect = fitz.Rect(*(float(value) for value in rect_values))
        _insert_textbox(
            page,
            rect,
            text,
            font_size,
            color,
            _align_from_name(fitz, item.get("align")),
        )


def draw_decoration_layout(page: Any, layout: dict[str, Any]) -> None:
    for item in layout.get("items") or []:
        if isinstance(item, dict):
            _draw_layout_item(page, item)


def _insert_text(
    page: Any,
    point: Any,
    text: str,
    font_size: float,
    color: tuple[float, float, float],
    morph: Any | None = None,
) -> None:
    kwargs: dict[str, Any] = {
        "fontsize": font_size,
        "color": color,
        "overlay": True,
        **text_insert_kwargs(),
    }
    if morph is not None:
        kwargs["morph"] = morph

    try:
        page.insert_text(point, text, **kwargs)
        return
    except TypeError:
        if morph is not None:
            kwargs.pop("morph", None)
            try:
                page.insert_text(point, text, **kwargs)
                return
            except Exception:
                pass
    except Exception:
        pass

    fallback_kwargs: dict[str, Any] = {
        "fontsize": font_size,
        "color": color,
        "overlay": True,
        "fontname": PDF_WORKBENCH_FALLBACK_FONT,
    }
    if morph is not None:
        fallback_kwargs["morph"] = morph
    try:
        page.insert_text(point, text, **fallback_kwargs)
        return
    except TypeError:
        if morph is not None:
            fallback_kwargs.pop("morph", None)
            try:
                page.insert_text(point, text, **fallback_kwargs)
                return
            except Exception:
                pass
    except Exception:
        pass

    page.insert_text(point, text, fontsize=font_size, color=color, overlay=True)


def _insert_textbox(
    page: Any,
    rect: Any,
    text: str,
    font_size: float,
    color: tuple[float, float, float],
    align: int,
) -> None:
    kwargs: dict[str, Any] = {
        "fontsize": font_size,
        "color": color,
        "align": align,
        "overlay": True,
        **text_insert_kwargs(),
    }
    try:
        page.insert_textbox(rect, text, **kwargs)
        return
    except Exception:
        pass

    fallback_kwargs: dict[str, Any] = {
        "fontsize": font_size,
        "color": color,
        "align": align,
        "overlay": True,
        "fontname": PDF_WORKBENCH_FALLBACK_FONT,
    }
    try:
        page.insert_textbox(rect, text, **fallback_kwargs)
        return
    except Exception:
        pass

    point = (rect.x0, rect.y0 + font_size)
    _insert_text(page, point, text, font_size, color)


def _applies_to_page(
    decoration: dict[str, Any],
    page_context: dict[str, Any] | None,
    output_index: int | None,
) -> bool:
    if page_context is None:
        return True

    page_id = page_context.get("pageId")
    if page_id and page_id in set(decoration.get("excludedPageIds") or []):
        return False
    target = decoration.get("target")
    decoration_page_id = decoration.get("pageId")
    if decoration_page_id:
        return decoration_page_id == page_id
    if target == "file":
        decoration_file_id = decoration.get("fileId")
        if not decoration_file_id:
            return False
        return decoration_file_id == page_context.get("fileId")
    if target == "selected":
        return bool(page_context.get("selected"))
    if target == "output":
        decoration_output = decoration.get("outputIndex")
        return decoration_output in (None, output_index)
    return True


def apply_decorations(
    input_file: Path,
    output_file: Path,
    decorations: list[dict[str, Any]],
    password: str = "",
    page_contexts: list[dict[str, Any]] | None = None,
    output_index: int | None = None,
) -> Path:
    if not decorations:
        if input_file != output_file:
            output_file.write_bytes(input_file.read_bytes())
        return output_file

    doc = open_fitz_document(input_file, password=password)
    try:
        total = len(doc)
        for page_index, page in enumerate(doc):
            rect = page.rect
            page_context = page_contexts[page_index] if page_contexts and page_index < len(page_contexts) else None
            layout = resolve_page_decoration_layout(
                rect,
                decorations,
                page_index,
                total,
                page_context,
                output_index,
            )
            for item in layout["items"]:
                _draw_layout_item(page, item)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = output_file.with_suffix(output_file.suffix + ".decor.tmp")
        doc.save(str(tmp_file), garbage=4, deflate=True)
    finally:
        doc.close()

    os.replace(tmp_file, output_file)
    return output_file
