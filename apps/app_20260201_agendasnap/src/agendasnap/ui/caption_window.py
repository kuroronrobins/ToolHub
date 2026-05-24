"""Live captions window for AgendaSnap."""
from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from collections import deque
from pathlib import Path

import flet as ft

from agendasnap.config.ai_providers import normalize_api_key_priority, resolve_text_runtime
from agendasnap.config.loader import load_config, save_config
from agendasnap.config.validate import validate_config
from agendasnap.llm.openai_responses import OpenAIResponsesClient, extract_output_json
from agendasnap.runtime_paths import resolve_session_root

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "default.yaml"
DEFAULT_CAPTION_FONT_SIZE = 20
DEFAULT_CAPTION_MIN_FONT_SIZE = 14
DEFAULT_CAPTION_MAX_FONT_SIZE = 64
CAPTION_FONT_STEP = 2


def clamp_caption_font_size(value: object, min_size: object = 14, max_size: object = 64) -> int:
    minimum = int(float(min_size or DEFAULT_CAPTION_MIN_FONT_SIZE))
    maximum = int(float(max_size or DEFAULT_CAPTION_MAX_FONT_SIZE))
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    try:
        size = int(round(float(value)))
    except (TypeError, ValueError):
        size = DEFAULT_CAPTION_FONT_SIZE
    return max(minimum, min(maximum, size))


def caption_font_settings(cfg: dict) -> tuple[int, int, int]:
    ui_cfg = cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}
    caption_cfg = ui_cfg.get("caption") if isinstance(ui_cfg.get("caption"), dict) else {}
    min_size = clamp_caption_font_size(
        caption_cfg.get("min_font_size", DEFAULT_CAPTION_MIN_FONT_SIZE),
        1,
        128,
    )
    max_size = clamp_caption_font_size(
        caption_cfg.get("max_font_size", DEFAULT_CAPTION_MAX_FONT_SIZE),
        min_size,
        128,
    )
    size = clamp_caption_font_size(
        caption_cfg.get("font_size", DEFAULT_CAPTION_FONT_SIZE),
        min_size,
        max_size,
    )
    return size, min_size, max_size


def adjust_caption_font_size(current: int, direction: int, min_size: int, max_size: int) -> int:
    step = CAPTION_FONT_STEP if int(direction) > 0 else -CAPTION_FONT_STEP
    return clamp_caption_font_size(int(current) + step, min_size, max_size)


def caption_font_direction_from_scroll(scroll_delta: object) -> int:
    try:
        delta = float(scroll_delta)
    except (TypeError, ValueError):
        return 0
    if delta < 0:
        return 1
    if delta > 0:
        return -1
    return 0


def _tail_transcript(
    path: Path,
    last_pos: int,
    buffer: deque[dict[str, object]],
    seq_counter: int,
    limit: int = 200,
) -> tuple[int, int, int, list[dict[str, object]]]:
    if not path.exists():
        return last_pos, 0, seq_counter, []
    size = path.stat().st_size
    if size < last_pos:
        last_pos = 0
    added = 0
    new_items: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        f.seek(last_pos)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                text = str(payload.get("text", "")).strip()
                source = str(payload.get("source", "")).strip()
                state = str(payload.get("state", "")).strip()
            except Exception:
                text = ""
                source = ""
                state = ""
            if text:
                item = {
                    "seq": seq_counter,
                    "text": text,
                    "source": source,
                    "state": state,
                }
                seq_counter += 1
                buffer.append(item)
                new_items.append(item)
                added += 1
                while len(buffer) > limit:
                    buffer.popleft()
        return f.tell(), added, seq_counter, new_items


def main(page: ft.Page) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-dir", type=Path, required=False)
    parser.add_argument("--session-root", type=Path, required=False)
    parser.add_argument("--config", type=Path, required=False)
    args, _unknown = parser.parse_known_args()

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("agendasnap.caption_window")

    config_path = args.config or DEFAULT_CONFIG_PATH
    cfg: dict = {}
    if config_path and Path(config_path).exists():
        try:
            cfg = load_config(Path(config_path))
            validate_config(cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Config load/validate failed: %s", exc)
            cfg = {}

    page.title = "AgendaSnap Captions"
    page.window.width = 640
    page.window.height = 360
    page.window.resizable = True
    page.window.title_bar_hidden = True
    page.window.title_bar_buttons_hidden = True
    page.window.always_on_top = True
    page.padding = 8
    page.bgcolor = "#111111"
    page.theme = ft.Theme(font_family="Yu Gothic UI")

    follow_latest = True
    showing_placeholder = False
    auto_scroll_pending = False
    ctrl_pressed = False
    caption_font_size, caption_min_font_size, caption_max_font_size = caption_font_settings(cfg)

    translation_cfg = cfg.get("translation") if isinstance(cfg.get("translation"), dict) else {}
    translation_enabled = bool(translation_cfg.get("enable", False))
    translation_panel_visible = bool(translation_cfg.get("panel_visible", True))
    target_language_mic = str(
        translation_cfg.get("target_language_mic")
        or translation_cfg.get("target_language")
        or "en"
    )
    target_language_sys = str(
        translation_cfg.get("target_language_sys")
        or translation_cfg.get("target_language")
        or "en"
    )
    batch_wait_ms = int(translation_cfg.get("batch_wait_ms", 200))
    batch_lines = int(translation_cfg.get("batch_lines", 3))
    batch_chars = int(translation_cfg.get("batch_chars", 300))
    request_timeout_seconds = float(translation_cfg.get("request_timeout_seconds", 20))
    max_output_tokens = int(translation_cfg.get("max_output_tokens", 400))
    backfill_lines = int(translation_cfg.get("backfill_lines", 20))
    secrets_cfg = cfg.get("secrets") if isinstance(cfg.get("secrets"), dict) else {}
    global_priority = normalize_api_key_priority(secrets_cfg.get("priority"))
    translation_runtime = resolve_text_runtime(
        translation_cfg,
        fallback_priority=global_priority,
        purpose="translation",
    )
    translation_model = str(translation_runtime.get("model") or "gpt-4o-mini")

    translation_cache: dict[tuple[str, str], str] = {}
    translations: dict[int, dict[str, str]] = {}
    seq_rule: dict[int, int] = {}
    pending_ids: set[int] = set()
    translate_queue: deque[dict[str, object]] = deque()
    queue_lock = threading.Lock()
    translation_cache_path: Path | None = None
    cache_loaded = False

    def _color_for_source(source: str) -> str:
        if source == "mic":
            return "#7CCBFF"
        if source == "sys":
            return "#FFB34D"
        return "#E5E7EB"

    def _translation_color_for_source(source: str) -> str:
        if source == "mic":
            return "#B9E3FF"
        if source == "sys":
            return "#FFD9A3"
        return "#CBD5E1"

    def _script_flags(text: str) -> tuple[bool, bool, bool, bool]:
        has_kana = False
        has_hangul = False
        has_cjk = False
        has_latin = False
        for ch in text:
            code = ord(ch)
            if 0x3040 <= code <= 0x30FF:
                has_kana = True
            elif 0xAC00 <= code <= 0xD7AF:
                has_hangul = True
            elif 0x4E00 <= code <= 0x9FFF:
                has_cjk = True
            elif 0x0041 <= code <= 0x005A or 0x0061 <= code <= 0x007A:
                has_latin = True
        return has_kana, has_hangul, has_cjk, has_latin

    def _matches_language(text: str, lang: str) -> bool:
        has_kana, has_hangul, has_cjk, has_latin = _script_flags(text)
        if lang == "ja":
            return has_kana or (has_cjk and not has_hangul and not has_latin)
        if lang == "zh":
            return has_cjk and not has_kana and not has_hangul
        if lang == "ko":
            return has_hangul
        if lang == "en":
            return has_latin and not (has_kana or has_hangul or has_cjk)
        return False

    def _select_rule_index(text: str) -> int | None:
        for idx, rule in enumerate(translation_rules):
            if _matches_language(text, rule["input"]):
                return idx
        return None

    def _make_text(item: dict[str, object]) -> ft.Text:
        color = _color_for_source(item.get("source", ""))
        if item.get("state") == "partial":
            color = "#A3A3A3"
        return ft.Text(
            item.get("text", ""),
            size=caption_font_size,
            color=color,
            text_align=ft.TextAlign.LEFT,
            selectable=True,
        )

    def _make_translation_text(item: dict[str, object], translated: str, lang: str) -> ft.Control:
        color = _translation_color_for_source(item.get("source", ""))
        label = dict(language_options).get(lang, lang)
        return ft.Container(
            padding=ft.padding.only(left=14),
            content=ft.Text(
                f"→ {label}: {translated}",
                size=max(12, caption_font_size - 2),
                color=color,
                italic=True,
                text_align=ft.TextAlign.LEFT,
                selectable=True,
            ),
        )

    follow_button = ft.IconButton(
        icon=ft.Icons.ARROW_DROP_DOWN_CIRCLE,
        icon_color="#7CCBFF",
        tooltip="Follow latest",
    )

    language_options = [
        ("ja", "日本語"),
        ("en", "English"),
        ("zh", "中文"),
        ("ko", "한국어"),
    ]
    language_values = [value for value, _label in language_options]

    def _sanitize_lang(value: str | None, default: str) -> str:
        if value in language_values:
            return str(value)
        return default

    target_language_mic = _sanitize_lang(target_language_mic, "en")
    target_language_sys = _sanitize_lang(target_language_sys, "en")

    def _normalize_rules(raw_rules: object) -> list[dict[str, str]]:
        rules: list[dict[str, str]] = []
        if isinstance(raw_rules, list):
            for entry in raw_rules:
                if not isinstance(entry, dict):
                    continue
                inp = _sanitize_lang(str(entry.get("input_language") or entry.get("input") or ""), "")
                out = _sanitize_lang(str(entry.get("output_language") or entry.get("output") or ""), "")
                if inp and out:
                    rules.append({"input": inp, "output": out})
        if not rules:
            rules = [
                {"input": "ja", "output": target_language_mic},
                {"input": "en", "output": target_language_sys},
            ]
        if len(rules) == 1:
            rules.append({"input": "en", "output": "ja" if rules[0]["input"] != "ja" else "en"})
        return rules[:2]

    translation_rules = _normalize_rules(translation_cfg.get("rules"))

    translate_button = ft.IconButton(
        icon=ft.Icons.LANGUAGE,
        icon_color="#7CCBFF" if translation_enabled else "#6B7280",
        tooltip="翻訳オン/オフ",
    )

    settings_button = ft.IconButton(
        icon=ft.Icons.TUNE,
        icon_color="#9CA3AF",
        tooltip="翻訳設定",
        visible=translation_enabled,
    )
    font_down_button = ft.IconButton(
        icon=ft.Icons.REMOVE,
        icon_color="#9CA3AF",
        tooltip="字幕を小さく",
        on_click=lambda _e: _change_caption_font(-1),
    )
    font_reset_button = ft.IconButton(
        icon=ft.Icons.TEXT_FIELDS,
        icon_color="#9CA3AF",
        tooltip="字幕サイズをリセット",
        on_click=lambda _e: _reset_caption_font(_e),
    )
    font_up_button = ft.IconButton(
        icon=ft.Icons.ADD,
        icon_color="#9CA3AF",
        tooltip="字幕を大きく",
        on_click=lambda _e: _change_caption_font(1),
    )

    rule_input_dropdowns: list[ft.Dropdown] = []
    rule_output_dropdowns: list[ft.Dropdown] = []
    for rule in translation_rules:
        rule_input_dropdowns.append(
            ft.Dropdown(
                options=[ft.dropdown.Option(value, label) for value, label in language_options],
                value=rule["input"],
                width=90,
                text_size=11,
                bgcolor="#1F2937",
                color="#E5E7EB",
                border_color="#374151",
                disabled=not translation_enabled,
            )
        )
        rule_output_dropdowns.append(
            ft.Dropdown(
                options=[ft.dropdown.Option(value, label) for value, label in language_options],
                value=rule["output"],
                width=90,
                text_size=11,
                bgcolor="#1F2937",
                color="#E5E7EB",
                border_color="#374151",
                disabled=not translation_enabled,
            )
        )

    list_view = ft.ListView(
        expand=True,
        spacing=6,
        auto_scroll=False,
    )

    def _rebuild_list() -> None:
        if not buffer or showing_placeholder:
            return
        items = list(buffer)
        controls: list[ft.Control] = []
        for item in items:
            controls.append(_make_text(item))
            if translation_enabled and item.get("state") == "final":
                entry = translations.get(int(item.get("seq", -1)))
                if entry:
                    controls.append(
                        _make_translation_text(item, entry.get("text", ""), entry.get("lang", ""))
                    )
        list_view.controls = controls

    def _save_caption_font_size() -> None:
        if not config_path:
            return
        path = Path(config_path)
        if not path.exists():
            return
        try:
            data = load_config(path)
        except Exception:  # noqa: BLE001
            data = {}
        if not isinstance(data, dict):
            data = {}
        ui_cfg = data.get("ui")
        if not isinstance(ui_cfg, dict):
            ui_cfg = {}
        caption_cfg = ui_cfg.get("caption")
        if not isinstance(caption_cfg, dict):
            caption_cfg = {}
        caption_cfg["font_size"] = int(caption_font_size)
        caption_cfg["min_font_size"] = int(caption_min_font_size)
        caption_cfg["max_font_size"] = int(caption_max_font_size)
        ui_cfg["caption"] = caption_cfg
        data["ui"] = ui_cfg
        try:
            save_config(path, data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save caption font size: %s", exc)

    def _set_caption_font_size(size: int, *, save: bool = True) -> None:
        nonlocal caption_font_size
        next_size = clamp_caption_font_size(size, caption_min_font_size, caption_max_font_size)
        if next_size == caption_font_size:
            return
        caption_font_size = next_size
        _rebuild_list()
        if save:
            _save_caption_font_size()
        page.update()

    def _change_caption_font(direction: int) -> None:
        _set_caption_font_size(
            adjust_caption_font_size(
                caption_font_size,
                direction,
                caption_min_font_size,
                caption_max_font_size,
            )
        )

    def _reset_caption_font(_e: ft.ControlEvent | None = None) -> None:
        _set_caption_font_size(DEFAULT_CAPTION_FONT_SIZE)

    def _handle_keyboard(e: ft.KeyboardEvent) -> None:
        nonlocal ctrl_pressed
        key = str(getattr(e, "key", "") or "").lower()
        if key in {"control", "controlleft", "controlright", "ctrl"}:
            ctrl_pressed = bool(getattr(e, "event_type", "") != "keyup")
            return
        ctrl_pressed = bool(getattr(e, "ctrl", False))

    def _set_follow(enabled: bool) -> None:
        nonlocal follow_latest
        follow_latest = enabled
        follow_button.icon_color = "#7CCBFF" if enabled else "#6B7280"
        page.update()

    def _scroll_to_bottom() -> None:
        nonlocal auto_scroll_pending
        auto_scroll_pending = True
        list_view.scroll_to(offset=1e9, duration=140)
        def _clear() -> None:
            nonlocal auto_scroll_pending
            auto_scroll_pending = False
        threading.Timer(0.5, _clear).start()

    def _handle_follow(_e: ft.ControlEvent) -> None:
        _set_follow(True)
        _scroll_to_bottom()

    def _handle_scroll(e: ft.OnScrollEvent) -> None:
        if ctrl_pressed and e.scroll_delta is not None:
            direction = caption_font_direction_from_scroll(e.scroll_delta)
            if direction:
                _change_caption_font(direction)
            return
        if not follow_latest:
            return
        if auto_scroll_pending:
            # Ignore programmatic scroll events
            return
        is_user = False
        if e.scroll_delta is not None and abs(e.scroll_delta) > 0:
            is_user = True
        elif e.velocity is not None and abs(e.velocity) > 0:
            is_user = True
        elif e.event_type in ("start", "update", "end"):
            is_user = True
        if not is_user:
            return
        if e.max_scroll_extent is None or e.max_scroll_extent <= 0:
            return
        if e.pixels < e.max_scroll_extent - 4:
            _set_follow(False)

    def _ensure_translation_cache_loaded() -> None:
        nonlocal cache_loaded
        if cache_loaded or translation_cache_path is None:
            return
        if translation_cache_path.exists():
            try:
                with translation_cache_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except Exception:
                            continue
                        text = str(payload.get("text", "")).strip()
                        lang = str(payload.get("lang", "")).strip()
                        translated = str(payload.get("translated", "")).strip()
                        if text and lang and translated:
                            translation_cache[(text, lang)] = translated
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load translation cache: %s", exc)
        cache_loaded = True

    def _append_translation_cache(text: str, lang: str, translated: str) -> None:
        if translation_cache_path is None:
            return
        try:
            with translation_cache_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"text": text, "lang": lang, "translated": translated}, ensure_ascii=False))
                f.write("\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to write translation cache: %s", exc)

    def _save_translation_rules() -> None:
        if not config_path:
            return
        path = Path(config_path)
        if not path.exists():
            return
        try:
            data = load_config(path)
        except Exception:  # noqa: BLE001
            data = {}
        if not isinstance(data, dict):
            data = {}
        translation = data.get("translation")
        if not isinstance(translation, dict):
            translation = {}
        translation["rules"] = [
            {"input_language": rule["input"], "output_language": rule["output"]}
            for rule in translation_rules
        ]
        translation["target_language_mic"] = translation_rules[0]["output"]
        translation["target_language_sys"] = translation_rules[1]["output"]
        translation["panel_visible"] = bool(translation_panel_visible)
        data["translation"] = translation
        try:
            save_config(path, data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save translation rules: %s", exc)

    def _enqueue_for_translation(items: list[dict[str, object]]) -> None:
        if not translation_enabled:
            return
        pending: list[dict[str, object]] = []
        for item in items:
            if item.get("state") != "final":
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            seq = int(item.get("seq", -1))
            if seq < 0:
                continue
            rule_index = _select_rule_index(text)
            if rule_index is None:
                continue
            lang = translation_rules[rule_index]["output"]
            cache_key = (text, lang)
            cached = translation_cache.get(cache_key)
            if cached:
                translations[seq] = {"text": cached, "lang": lang}
                seq_rule[seq] = rule_index
                continue
            if seq in pending_ids or seq in translations:
                continue
            pending.append(
                {"seq": seq, "text": text, "lang": lang, "rule": rule_index, "ts": time.monotonic()}
            )
        if not pending:
            return
        with queue_lock:
            for item in pending:
                translate_queue.append(item)
                pending_ids.add(int(item["seq"]))
                seq_rule[int(item["seq"])] = int(item.get("rule", -1))

    def _enqueue_backfill() -> None:
        if not translation_enabled:
            return
        if not buffer:
            return
        items = list(buffer)[-max(backfill_lines, 0) :]
        _enqueue_for_translation(items)

    def _clear_rule_pending(rule_index: int) -> None:
        to_clear = {seq for seq, idx in seq_rule.items() if idx == rule_index}
        if not to_clear:
            return
        for seq in to_clear:
            translations.pop(seq, None)
            pending_ids.discard(seq)
            seq_rule.pop(seq, None)
        with queue_lock:
            if translate_queue:
                filtered = deque(
                    item for item in translate_queue if int(item.get("seq", -1)) not in to_clear
                )
                translate_queue.clear()
                translate_queue.extend(filtered)

    def _set_translation_enabled(enabled: bool) -> None:
        nonlocal translation_enabled, translation_panel_visible
        translation_enabled = enabled
        translate_button.icon_color = "#7CCBFF" if enabled else "#6B7280"
        settings_button.visible = enabled
        for ctrl in rule_input_dropdowns + rule_output_dropdowns:
            ctrl.disabled = not enabled
        if not enabled:
            with queue_lock:
                translate_queue.clear()
                pending_ids.clear()
        else:
            _enqueue_backfill()
        _update_translation_panel()
        _rebuild_list()
        page.update()

    def _handle_translation_toggle(_e: ft.ControlEvent) -> None:
        _set_translation_enabled(not translation_enabled)

    def _toggle_translation_panel(_e: ft.ControlEvent) -> None:
        nonlocal translation_panel_visible
        if not translation_enabled:
            return
        translation_panel_visible = not translation_panel_visible
        _update_translation_panel()
        _save_translation_rules()
        page.update()

    def _handle_rule_input_change(index: int, e: ft.ControlEvent) -> None:
        value = _sanitize_lang(str(e.control.value or ""), translation_rules[index]["input"])
        if value == translation_rules[index]["input"]:
            return
        translation_rules[index]["input"] = value
        _clear_rule_pending(index)
        _enqueue_backfill()
        _save_translation_rules()
        _rebuild_list()
        page.update()

    def _handle_rule_output_change(index: int, e: ft.ControlEvent) -> None:
        value = _sanitize_lang(str(e.control.value or ""), translation_rules[index]["output"])
        if value == translation_rules[index]["output"]:
            return
        translation_rules[index]["output"] = value
        _clear_rule_pending(index)
        _enqueue_backfill()
        _save_translation_rules()
        _rebuild_list()
        page.update()

    follow_button.on_click = _handle_follow
    list_view.on_scroll = _handle_scroll
    page.on_keyboard_event = _handle_keyboard
    translate_button.on_click = _handle_translation_toggle
    settings_button.on_click = _toggle_translation_panel
    for idx, ctrl in enumerate(rule_input_dropdowns):
        ctrl.on_change = lambda e, i=idx: _handle_rule_input_change(i, e)
    for idx, ctrl in enumerate(rule_output_dropdowns):
        ctrl.on_change = lambda e, i=idx: _handle_rule_output_change(i, e)

    close_button = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_color="#E5E7EB",
        tooltip="Close",
    )

    def _show_closing() -> None:
        page.snack_bar = ft.SnackBar(
            ft.Text("終了中..", color="#111111"),
            bgcolor="#FFFFFF",
            duration=2000,
        )
        page.snack_bar.open = True
        page.update()

    def _close_window(_e: ft.ControlEvent) -> None:
        _show_closing()
        def _do_destroy() -> None:
            try:
                page.window.destroy()
            except Exception:
                try:
                    page.window.close()
                except Exception:
                    pass
        threading.Timer(0.0, _do_destroy).start()

    close_button.on_click = _close_window
    page.on_close = _close_window

    drag_area = ft.WindowDragArea(
        content=ft.Container(height=32, bgcolor="#00000000")
    )

    rule_rows = ft.Column(
        spacing=1,
        controls=[
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("R1", size=10, color="#9CA3AF"),
                    rule_input_dropdowns[0],
                    ft.Icon(ft.Icons.ARROW_RIGHT_ALT, size=14, color="#9CA3AF"),
                    rule_output_dropdowns[0],
                ],
            ),
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("R2", size=10, color="#9CA3AF"),
                    rule_input_dropdowns[1],
                    ft.Icon(ft.Icons.ARROW_RIGHT_ALT, size=14, color="#9CA3AF"),
                    rule_output_dropdowns[1],
                ],
            ),
        ],
    )

    panel_container = ft.Container(
        visible=translation_enabled and translation_panel_visible,
        content=rule_rows,
    )

    def _update_translation_panel() -> None:
        panel_container.visible = translation_enabled and translation_panel_visible
        top_chrome.height = 96 if panel_container.visible else 36

    top_chrome = ft.Container(
        height=96 if (translation_enabled and translation_panel_visible) else 36,
        padding=ft.padding.only(top=2, left=2, right=2),
        content=ft.Row(
            expand=True,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Container(expand=True, content=drag_area),
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        translate_button,
                        settings_button,
                        font_down_button,
                        font_reset_button,
                        font_up_button,
                        panel_container,
                    ],
                ),
                close_button,
            ],
        ),
    )

    follow_overlay = ft.Container(
        right=6,
        bottom=6,
        content=follow_button,
    )

    page.add(
        ft.Column(
            expand=True,
            spacing=4,
            controls=[
                top_chrome,
                ft.Stack(
                    expand=True,
                    controls=[
                        ft.Container(
                            expand=True,
                            padding=ft.padding.only(left=4, right=4, top=2, bottom=4),
                            content=list_view,
                        ),
                        follow_overlay,
                    ],
                ),
            ],
        )
    )

    session_root = args.session_root or (
        args.session_dir.parent if args.session_dir else resolve_session_root("sessions")
    )
    transcript_path = args.session_dir / "transcript.jsonl" if args.session_dir else None
    if transcript_path is not None:
        translation_cache_path = transcript_path.with_name("translations.jsonl")
        _ensure_translation_cache_loaded()
    baseline_session: str | None = transcript_path.parent.name if transcript_path else None
    if transcript_path is None and session_root.exists():
        candidates = [p for p in session_root.iterdir() if p.is_dir()]
        if candidates:
            candidates.sort(key=lambda p: p.name)
            baseline_session = candidates[-1].name
    buffer: deque[dict[str, object]] = deque()
    last_pos = 0
    rendered_count = 0
    seq_counter = 0
    translator_client: OpenAIResponsesClient | None = None

    def _build_translation_payload(batch: list[dict[str, object]]) -> dict:
        lines = []
        for item in batch:
            seq = int(item.get("seq", -1))
            text = str(item.get("text", ""))
            lang = str(item.get("lang", ""))
            rule_index = int(item.get("rule", -1))
            input_lang = ""
            if 0 <= rule_index < len(translation_rules):
                input_lang = translation_rules[rule_index]["input"]
            lines.append(
                {
                    "id": seq,
                    "text": text,
                    "input_language": input_lang,
                    "target_language": lang,
                }
            )
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "translations": {
                    "type": "array",
                    "additionalProperties": False,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "integer"},
                            "text": {"type": "string"},
                        },
                        "required": ["id", "text"],
                    },
                }
            },
            "required": ["translations"],
        }
        user_payload = json.dumps({"lines": lines}, ensure_ascii=False)
        return {
            "model": translation_model,
            "input": [
                {
                    "role": "system",
                    "content": "You are a translation engine. Translate each line into its target_language. "
                    "Use input_language as a hint. Return JSON that matches the provided schema. "
                    "Do not omit any lines.",
                },
                {"role": "user", "content": user_payload},
            ],
            "temperature": 0.0,
            "max_output_tokens": max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "translations",
                    "schema": schema,
                    "strict": True,
                }
            },
        }

    def _call_translate(batch: list[dict[str, object]]) -> dict[int, str]:
        nonlocal translator_client
        if translator_client is None:
            translator_client = OpenAIResponsesClient(
                provider=str(translation_runtime.get("provider") or "openai"),
                api_key_priority=list(translation_runtime.get("api_key_priority") or ["env"]),
                api_key_service=str(translation_runtime.get("api_key_service") or "openai"),
                base_url=str(translation_runtime.get("base_url") or ""),
                timeout_seconds=request_timeout_seconds,
            )
        payload = _build_translation_payload(batch)
        resp = translator_client.request_json(payload)
        data = extract_output_json(resp)
        items = data.get("translations") if isinstance(data, dict) else None
        result: dict[int, str] = {}
        if isinstance(items, list):
            for entry in items:
                try:
                    seq = int(entry.get("id"))
                    text = str(entry.get("text", "")).strip()
                except Exception:
                    continue
                if text:
                    result[seq] = text
        return result

    def _collect_batch() -> list[dict[str, object]]:
        if not translation_enabled:
            return []
        with queue_lock:
            if not translate_queue:
                return []
            first_ts = float(translate_queue[0].get("ts", time.monotonic()))
            queue_size = len(translate_queue)
        if queue_size < batch_lines:
            wait_s = (batch_wait_ms / 1000.0) - (time.monotonic() - first_ts)
            if wait_s > 0:
                time.sleep(min(wait_s, 0.05))
        batch: list[dict[str, object]] = []
        total_chars = 0
        with queue_lock:
            if not translate_queue:
                return []
            while translate_queue and len(batch) < batch_lines:
                item = translate_queue[0]
                text = str(item.get("text", ""))
                if total_chars + len(text) > batch_chars and batch:
                    break
                translate_queue.popleft()
                batch.append(item)
                total_chars += len(text)
        return batch

    def _translate_worker() -> None:
        while True:
            if not translation_enabled:
                time.sleep(0.1)
                continue
            batch = _collect_batch()
            if not batch:
                time.sleep(0.05)
                continue
            text_map = {int(item["seq"]): str(item["text"]) for item in batch}
            lang_map = {int(item["seq"]): str(item.get("lang", "")) for item in batch}
            try:
                result = _call_translate(batch)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Translation failed: %s", exc)
                for seq in text_map:
                    pending_ids.discard(seq)
                time.sleep(0.1)
                continue
            updated = False
            for seq, translated in result.items():
                original = text_map.get(seq)
                if not original:
                    continue
                lang = lang_map.get(seq, "")
                translations[seq] = {"text": translated, "lang": lang}
                if lang:
                    translation_cache[(original, lang)] = translated
                    _append_translation_cache(original, lang, translated)
                pending_ids.discard(seq)
                updated = True
            if updated:
                _rebuild_list()
                if follow_latest and not showing_placeholder:
                    _scroll_to_bottom()
                page.update()

    def _poll() -> None:
        nonlocal last_pos, rendered_count, showing_placeholder, transcript_path, baseline_session
        nonlocal seq_counter, translation_cache_path, cache_loaded
        while True:
            added_lines = False
            reset_lines = False
            if session_root.exists():
                candidates = [p for p in session_root.iterdir() if p.is_dir()]
                if candidates:
                    candidates.sort(key=lambda p: p.name)
                    candidate = candidates[-1]
                    candidate_file = candidate / "transcript.jsonl"
                    current_name = transcript_path.parent.name if transcript_path else None
                    if candidate_file.exists() and candidate.name != current_name:
                        transcript_path = candidate_file
                        baseline_session = candidate.name
                        buffer.clear()
                        last_pos = 0
                        rendered_count = 0
                        seq_counter = 0
                        translations.clear()
                        seq_rule.clear()
                        pending_ids.clear()
                        with queue_lock:
                            translate_queue.clear()
                        list_view.controls = []
                        showing_placeholder = False
                        translation_cache_path = transcript_path.with_name("translations.jsonl")
                        cache_loaded = False
                        _ensure_translation_cache_loaded()
            if transcript_path is None:
                list_view.controls = [
                    ft.Text(
                        "Waiting for session...",
                        size=20,
                        color="#A3A3A3",
                        text_align=ft.TextAlign.LEFT,
                    )
                ]
                showing_placeholder = True
                page.update()
                time.sleep(0.7)
                continue

            last_pos, added_count, seq_counter, new_items = _tail_transcript(
                transcript_path,
                last_pos,
                buffer,
                seq_counter,
                limit=200,
            )
            if new_items:
                _enqueue_for_translation(new_items)
            if buffer:
                if showing_placeholder:
                    list_view.controls = []
                    rendered_count = 0
                    showing_placeholder = False
                    reset_lines = True
                if len(buffer) != rendered_count or added_count > 0:
                    _rebuild_list()
                    if len(buffer) < rendered_count:
                        reset_lines = True
                    elif len(buffer) > rendered_count:
                        added_lines = True
                    elif added_count > 0:
                        reset_lines = True
                    rendered_count = len(buffer)
            else:
                list_view.controls = [
                    ft.Text(
                        "Waiting for transcript...",
                        size=20,
                        color="#A3A3A3",
                        text_align=ft.TextAlign.LEFT,
                    )
                ]
                rendered_count = 0
                showing_placeholder = True
            if follow_latest and not showing_placeholder and (added_lines or reset_lines):
                _scroll_to_bottom()
            page.update()
            time.sleep(0.7)

    page.run_thread(_poll)
    page.run_thread(_translate_worker)


if __name__ == "__main__":
    ft.app(target=main)
