"""Live minutes window for AgendaSnap."""
from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import time
from pathlib import Path

import flet as ft


def main(page: ft.Page) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-dir", type=Path, required=False)
    args, _unknown = parser.parse_known_args()

    page.title = "AgendaSnap Minutes"
    page.window.width = 720
    page.window.height = 540
    page.window.resizable = True
    page.padding = 16
    page.bgcolor = "#FFFFFF"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(font_family="Yu Gothic UI")
    page.scroll = ft.ScrollMode.AUTO

    view_mode = {"value": "realtime"}
    current_md = {"value": "Session not set"}
    current_source = {"path": None, "label": ""}
    is_editing = {"value": False}

    md_style = ft.MarkdownStyleSheet(
        a_text_style=ft.TextStyle(color="#1D4ED8", decoration=ft.TextDecoration.UNDERLINE),
        p_text_style=ft.TextStyle(color="#111111", size=14),
        h1_text_style=ft.TextStyle(color="#111111", size=24, weight=ft.FontWeight.W_700),
        h2_text_style=ft.TextStyle(color="#111111", size=20, weight=ft.FontWeight.W_700),
        h3_text_style=ft.TextStyle(color="#111111", size=18, weight=ft.FontWeight.W_600),
        h4_text_style=ft.TextStyle(color="#111111", size=16, weight=ft.FontWeight.W_600),
        h5_text_style=ft.TextStyle(color="#111111", size=15, weight=ft.FontWeight.W_600),
        h6_text_style=ft.TextStyle(color="#111111", size=14, weight=ft.FontWeight.W_600),
        list_bullet_text_style=ft.TextStyle(color="#111111"),
        table_head_text_style=ft.TextStyle(color="#111111", weight=ft.FontWeight.W_600),
        table_body_text_style=ft.TextStyle(color="#111111"),
        blockquote_text_style=ft.TextStyle(color="#374151"),
        code_text_style=ft.TextStyle(color="#111111"),
    )
    md = ft.Markdown(current_md["value"], selectable=True, md_style_sheet=md_style)

    info_text = ft.Text("", size=14, color="#6B7280")
    finalize_status_text = ft.Text("", size=13, color="#64748B")
    update_list = ft.Column(spacing=6)
    update_panel = ft.Container(
        visible=False,
        opacity=0.0,
        animate_opacity=ft.Animation(300, "easeOut"),
        padding=ft.padding.symmetric(horizontal=12, vertical=10),
        border_radius=12,
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=["#EFF6FF", "#F8FAFC"],
        ),
        border=ft.border.all(1, "#BFDBFE"),
        content=ft.Column(
            spacing=6,
            controls=[
                ft.Text("Realtime updates", size=12, weight=ft.FontWeight.W_600, color="#2563EB"),
                update_list,
            ],
        ),
    )
    update_panel_state = {"until": 0.0}

    realtime_btn = ft.ElevatedButton("Realtime")
    final_btn = ft.ElevatedButton("Final")
    edit_btn = ft.OutlinedButton("Edit")
    button_style = ft.ButtonStyle(color="#1F2937")
    final_btn_style = ft.ButtonStyle(
        color={
            ft.ControlState.DEFAULT: "#1F2937",
            ft.ControlState.DISABLED: "#9CA3AF",
        },
        bgcolor={
            ft.ControlState.DISABLED: "#E5E7EB",
        },
        side={
            ft.ControlState.DISABLED: ft.border.BorderSide(1, "#D1D5DB"),
        },
        elevation={
            ft.ControlState.DISABLED: 0,
        },
    )
    realtime_btn.style = button_style
    final_btn.style = final_btn_style
    edit_btn.style = button_style
    final_btn_wrap = ft.Container(content=final_btn)

    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)

    if not args.session_dir:
        page.add(md)
        return

    minutes_path = args.session_dir / "minutes.md"
    minutes_json_path = args.session_dir / "minutes.json"
    minutes_realtime_path = args.session_dir / "minutes_realtime.md"
    status_path = args.session_dir / "status.json"
    last_content = ""
    last_mode = ""
    last_finalize_status = ""

    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _is_final_minutes(data: dict | None) -> bool:
        return isinstance(data, dict) and "meeting_info" in data

    def _is_realtime_minutes(data: dict | None) -> bool:
        return isinstance(data, dict) and "meta" in data

    finalize_active_states = {
        "running",
        "provisional_finalize",
        "catch_up_prepare",
        "catch_up_stt",
        "catch_up_finalize",
    }

    def _to_float(value: object) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _format_duration(seconds: float | None) -> str:
        if seconds is None:
            return "-"
        total = max(0, int(round(float(seconds))))
        mins, sec = divmod(total, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h {mins:02d}m"
        if mins > 0:
            return f"{mins}m {sec:02d}s"
        return f"{sec}s"

    def _finalize_payload(status_json: dict | None) -> dict:
        if not isinstance(status_json, dict):
            return {}
        payload = status_json.get("minutes_finalize")
        return payload if isinstance(payload, dict) else {}

    def _is_recording_active(status_json: dict | None) -> bool:
        if not isinstance(status_json, dict):
            return False

        pipeline = status_json.get("pipeline")
        phase = ""
        if isinstance(pipeline, dict):
            phase = str(pipeline.get("phase", "")).strip().lower()
        if phase in {"running", "stopping"}:
            return True

        finalize = _finalize_payload(status_json)
        state = str(finalize.get("state", "")).strip().lower()
        if state in finalize_active_states:
            return True

        ts = status_json.get("timestamp")
        if isinstance(ts, (int, float)):
            return (time.time() - float(ts)) <= 20.0
        return False

    def _finalize_status_summary(status_json: dict | None) -> str:
        finalize = _finalize_payload(status_json)
        if not finalize:
            return ""

        state = str(finalize.get("state", "")).strip().lower()
        if not state:
            return ""

        message = str(finalize.get("message", "")).strip()
        error = str(finalize.get("error", "")).strip()
        updated_at = _to_float(finalize.get("updated_at"))
        started_at = _to_float(finalize.get("started_at"))
        now = time.time()
        elapsed = (now - started_at) if started_at is not None else None
        stale = bool(updated_at is not None and (now - updated_at) > 45.0)

        progress_current = int(finalize.get("progress_current", 0) or 0)
        progress_total = int(finalize.get("progress_total", 0) or 0)
        progress_ratio = _to_float(finalize.get("progress_ratio"))
        if progress_ratio is None and progress_total > 0:
            progress_ratio = progress_current / progress_total
        eta_seconds = _to_float(finalize.get("eta_seconds"))

        if state in finalize_active_states:
            if progress_total > 0:
                progress_part = f" {progress_current}/{progress_total}"
            elif progress_ratio is not None:
                progress_part = f" {max(0.0, min(1.0, progress_ratio)) * 100:.0f}%"
            else:
                progress_part = ""
            eta_part = f" ETA {_format_duration(eta_seconds)}" if eta_seconds is not None and eta_seconds > 0 else ""
            elapsed_part = f" elapsed {_format_duration(elapsed)}" if elapsed is not None else ""
            stale_part = " (stalled?)" if stale else ""
            return f"Finalizing{progress_part}{eta_part}{elapsed_part}{stale_part}"

        if state == "completed":
            return "Final minutes ready"
        if state == "failed":
            detail = error or message or "unknown error"
            return f"Finalization failed: {detail}"
        return message or state

    def _load_markdown(path: Path, fallback: str) -> str:
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                return fallback
        return fallback

    def _resolve_realtime_markdown(minutes_json: dict | None) -> tuple[str, Path | None]:
        if minutes_realtime_path.exists():
            return _load_markdown(minutes_realtime_path, "Realtime minutes are not available yet."), minutes_realtime_path
        if _is_realtime_minutes(minutes_json) and minutes_path.exists():
            return _load_markdown(minutes_path, "Realtime minutes are not available yet."), minutes_path
        return "Realtime minutes are not available yet.", None

    def _resolve_final_markdown(minutes_json: dict | None) -> tuple[str, Path | None]:
        if _is_final_minutes(minutes_json) and minutes_path.exists():
            return _load_markdown(minutes_path, "Final minutes are not available yet."), minutes_path
        return "Final minutes are not available yet.", None

    def _update_mode_button_styles() -> None:
        if view_mode["value"] == "realtime":
            realtime_btn.disabled = False
            realtime_btn.bgcolor = "#E0ECFF"
            final_btn.bgcolor = None
        else:
            final_btn.bgcolor = "#E0ECFF" if not final_btn.disabled else None
            realtime_btn.bgcolor = None

    def _final_disabled_reason(minutes_json: dict | None, status_json: dict | None) -> str | None:
        finalize_summary = _finalize_status_summary(status_json)
        if _is_recording_active(status_json):
            return finalize_summary or "録音/文字起こし中または清書処理中です"
        if not _is_final_minutes(minutes_json):
            return "清書議事録が未生成です"
        return None

    def _update_buttons(minutes_json: dict | None, status_json: dict | None) -> None:
        reason = _final_disabled_reason(minutes_json, status_json)
        final_btn.disabled = reason is not None
        final_btn.icon = ft.Icons.LOCK_OUTLINE if final_btn.disabled else None
        final_btn.tooltip = reason or "清書議事録を表示"
        final_btn_wrap.tooltip = final_btn.tooltip

    def _set_view_mode(mode: str) -> None:
        view_mode["value"] = mode
        _update_mode_button_styles()
        page.update()

    def _show_snack(message: str, *, error: bool = False) -> None:
        page.snack_bar = ft.SnackBar(
            ft.Text(message),
            bgcolor="#FEE2E2" if error else "#E7F7EE",
        )
        page.snack_bar.open = True
        page.update()

    def _diff_inserted_lines(old_text: str, new_text: str) -> list[tuple[int, str]]:
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()
        matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
        inserted: list[tuple[int, str]] = []
        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
            if tag in {"insert", "replace"}:
                for offset, line in enumerate(new_lines[j1:j2]):
                    inserted.append((j1 + offset + 1, line))
        return inserted

    def _show_update_panel(inserted: list[tuple[int, str]]) -> None:
        if not inserted:
            return
        items: list[ft.Control] = []
        max_items = 6
        for line_no, line in inserted[:max_items]:
            text = line.strip()
            if not text:
                continue
            if len(text) > 140:
                text = f"{text[:140]}..."
            items.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=8, vertical=6),
                    border_radius=8,
                    bgcolor="#DBEAFE",
                    border=ft.border.all(1, "#93C5FD"),
                    content=ft.Text(f"L{line_no}: {text}", size=12, color="#1F2937"),
                )
            )
        if len(inserted) > max_items:
            items.append(ft.Text(f"+{len(inserted) - max_items} more", size=11, color="#4B5563"))
        if not items:
            return
        update_list.controls = items
        update_panel.visible = True
        update_panel.opacity = 1.0
        page.update()

        until = time.time() + 4.0
        update_panel_state["until"] = until

        def _hide_later(target: float) -> None:
            sleep_for = max(0.0, target - time.time())
            if sleep_for > 0:
                time.sleep(sleep_for)
            if update_panel_state["until"] != target:
                return
            update_panel.opacity = 0.0
            page.update()
            time.sleep(0.35)
            if update_panel_state["until"] != target:
                return
            update_panel.visible = False
            page.update()

        page.run_thread(_hide_later, until)

    def _copy_to_clipboard(_e: ft.ControlEvent) -> None:
        if not current_md["value"].strip():
            _show_snack("Nothing to copy.", error=True)
            return
        page.set_clipboard(current_md["value"])
        _show_snack("Copied to clipboard.")

    def _split_table_row(line: str) -> list[str]:
        raw = line.strip()
        if raw.startswith("|"):
            raw = raw[1:]
        if raw.endswith("|"):
            raw = raw[:-1]
        return [cell.strip() for cell in raw.split("|")]

    def _table_alignments(sep_line: str, count: int) -> list[str]:
        cells = _split_table_row(sep_line)
        aligns: list[str] = []
        for idx in range(count):
            cell = cells[idx] if idx < len(cells) else ""
            left = cell.strip().startswith(":")
            right = cell.strip().endswith(":")
            if left and right:
                aligns.append("center")
            elif right:
                aligns.append("right")
            else:
                aligns.append("left")
        return aligns

    def _build_table_html(headers: list[str], rows: list[list[str]], aligns: list[str]) -> str:
        def _cell(tag: str, text: str, align: str) -> str:
            escaped = html.escape(text)
            return f"<{tag} style=\"text-align: {align};\">{escaped}</{tag}>"

        head_cells = "".join(
            _cell("th", headers[idx] if idx < len(headers) else "", aligns[idx])
            for idx in range(len(headers))
        )
        body_rows = []
        for row in rows:
            row_cells = "".join(
                _cell("td", row[idx] if idx < len(row) else "", aligns[idx])
                for idx in range(len(headers))
            )
            body_rows.append(f"<tr>{row_cells}</tr>")
        return "<table><thead><tr>" + head_cells + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"

    def _convert_markdown_tables(markdown_text: str) -> str:
        table_sep = re.compile(r"^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")
        lines = markdown_text.splitlines()
        out: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if (
                i + 1 < len(lines)
                and "|" in line
                and table_sep.match(lines[i + 1] or "")
            ):
                headers = _split_table_row(line)
                aligns = _table_alignments(lines[i + 1], len(headers))
                i += 2
                rows: list[list[str]] = []
                while i < len(lines) and lines[i].strip():
                    if table_sep.match(lines[i] or "") or "|" not in lines[i]:
                        break
                    rows.append(_split_table_row(lines[i]))
                    i += 1
                out.append(_build_table_html(headers, rows, aligns))
                continue
            out.append(line)
            i += 1
        return "\n".join(out)

    def _render_markdown(markdown_text: str) -> str:
        text = markdown_text or ""
        try:
            import markdown as md  # type: ignore

            return md.markdown(
                text,
                extensions=["extra", "tables", "fenced_code", "sane_lists"],
                output_format="html5",
            )
        except Exception:
            pass
        try:
            from markdown_it import MarkdownIt  # type: ignore

            prepared = _convert_markdown_tables(text)
            return MarkdownIt("commonmark", {"html": True, "breaks": True}).render(prepared)
        except Exception:
            escaped = html.escape(text)
            return f"<pre>{escaped}</pre>"

    def _build_html_document(markdown_text: str) -> str:
        body_html = _render_markdown(markdown_text)
        return (
            "<!doctype html>\n"
            "<html lang=\"ja\">\n"
            "<head>\n"
            "  <meta charset=\"utf-8\">\n"
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "  <title>AgendaSnap Minutes</title>\n"
            "  <style>\n"
            "    :root { color-scheme: light; }\n"
            "    body { margin: 0; background: #FFFFFF; color: #111111; }\n"
            "    .markdown-body {\n"
            "      font-family: \"Yu Gothic UI\", \"Hiragino Kaku Gothic ProN\", Arial, sans-serif;\n"
            "      max-width: 960px;\n"
            "      margin: 0 auto;\n"
            "      padding: 24px;\n"
            "      line-height: 1.7;\n"
            "    }\n"
            "    .markdown-body h1, .markdown-body h2, .markdown-body h3,\n"
            "    .markdown-body h4, .markdown-body h5, .markdown-body h6 {\n"
            "      color: #111111;\n"
            "      margin-top: 1.2em;\n"
            "      margin-bottom: 0.6em;\n"
            "      font-weight: 700;\n"
            "    }\n"
            "    .markdown-body h1 { font-size: 24px; border-bottom: 1px solid #E5E7EB; padding-bottom: 6px; }\n"
            "    .markdown-body h2 { font-size: 20px; border-bottom: 1px solid #F3F4F6; padding-bottom: 4px; }\n"
            "    .markdown-body h3 { font-size: 18px; }\n"
            "    .markdown-body p { margin: 0.6em 0; }\n"
            "    .markdown-body ul, .markdown-body ol { padding-left: 1.4em; }\n"
            "    .markdown-body li { margin: 0.3em 0; }\n"
            "    .markdown-body a { color: #1D4ED8; text-decoration: underline; }\n"
            "    .markdown-body blockquote {\n"
            "      border-left: 4px solid #E5E7EB;\n"
            "      margin: 0.8em 0;\n"
            "      padding: 0.4em 0.9em;\n"
            "      color: #374151;\n"
            "      background: #F9FAFB;\n"
            "    }\n"
            "    .markdown-body table { border-collapse: collapse; margin: 12px 0; width: 100%; }\n"
            "    .markdown-body th, .markdown-body td { border: 1px solid #E5E7EB; padding: 6px 10px; }\n"
            "    .markdown-body th { background: #F3F4F6; text-align: left; }\n"
            "    .markdown-body code {\n"
            "      background: #F3F4F6;\n"
            "      padding: 2px 4px;\n"
            "      border-radius: 4px;\n"
            "      font-family: \"Cascadia Mono\", \"Consolas\", monospace;\n"
            "      font-size: 0.95em;\n"
            "    }\n"
            "    .markdown-body pre {\n"
            "      background: #F3F4F6;\n"
            "      padding: 12px;\n"
            "      border-radius: 6px;\n"
            "      overflow-x: auto;\n"
            "    }\n"
            "    .markdown-body pre code { background: transparent; padding: 0; }\n"
            "  </style>\n"
            "</head>\n"
            "<body>\n"
            f"<main class=\"markdown-body\">{body_html}</main>\n"
            "</body>\n"
            "</html>\n"
        )

    def _save_html(path: str) -> None:
        if not path:
            return
        try:
            Path(path).write_text(_build_html_document(current_md["value"]), encoding="utf-8")
            _show_snack("HTML saved")
        except Exception as exc:  # noqa: BLE001
            _show_snack(f"Save failed: {exc}", error=True)

    def _start_html_save(_e: ft.ControlEvent | None = None) -> None:
        file_picker.save_file(
            dialog_title="Save minutes as HTML",
            file_name="minutes.html",
            allowed_extensions=["html"],
        )

    editor = ft.TextField(
        value="",
        multiline=True,
        expand=True,
        min_lines=20,
        text_size=14,
        text_style=ft.TextStyle(color="#111111"),
    )

    def _enter_edit_mode() -> None:
        if is_editing["value"]:
            return
        editor.value = current_md["value"]
        is_editing["value"] = True
        edit_btn.text = "Editing..."
        info_text.value = "Editing mode: save to overwrite the current minutes file."
        editor_actions.visible = True
        editor.visible = True
        md.visible = False
        page.update()

    def _exit_edit_mode() -> None:
        if not is_editing["value"]:
            return
        is_editing["value"] = False
        edit_btn.text = "Edit"
        editor_actions.visible = False
        editor.visible = False
        md.visible = True
        page.update()

    def _save_edit() -> None:
        path = current_source.get("path")
        if path is None:
            _show_snack("No target file to save.", error=True)
            return
        try:
            Path(path).write_text(editor.value or "", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            _show_snack(f"Save failed: {exc}", error=True)
            return
        current_md["value"] = editor.value or ""
        md.value = current_md["value"]
        _show_snack("Saved.")
        _exit_edit_mode()

    def _cancel_edit() -> None:
        _exit_edit_mode()

    def _toggle_edit(_e: ft.ControlEvent) -> None:
        if is_editing["value"]:
            _exit_edit_mode()
        else:
            _enter_edit_mode()

    def _on_save_result(e: ft.FilePickerResultEvent) -> None:
        if not e.path:
            return
        _save_html(e.path)

    file_picker.on_result = _on_save_result

    def _select_realtime(_e: ft.ControlEvent) -> None:
        _set_view_mode("realtime")

    def _select_final(_e: ft.ControlEvent) -> None:
        if final_btn.disabled:
            return
        _set_view_mode("final")

    realtime_btn.on_click = _select_realtime
    final_btn.on_click = _select_final
    edit_btn.on_click = _toggle_edit

    header = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[
            ft.Row(
                spacing=8,
                controls=[realtime_btn, final_btn_wrap, edit_btn],
            ),
            ft.Row(
                spacing=8,
                controls=[
                    ft.PopupMenuButton(
                        content=ft.Container(
                            padding=ft.padding.symmetric(horizontal=14, vertical=8),
                            border=ft.border.all(1, "#CBD5F5"),
                            border_radius=16,
                            bgcolor="#FFFFFF",
                            content=ft.Text("Output", color="#1F2937"),
                        ),
                        items=[
                            ft.PopupMenuItem(text="Copy", on_click=_copy_to_clipboard),
                            ft.PopupMenuItem(text="Save as HTML", on_click=_start_html_save),
                        ],
                    )
                ],
            ),
        ],
    )

    editor_actions = ft.Row(
        spacing=8,
        controls=[
            ft.ElevatedButton("Save", on_click=lambda _e: _save_edit()),
            ft.OutlinedButton("Cancel", on_click=lambda _e: _cancel_edit()),
        ],
        visible=False,
    )

    content = ft.Column(
        expand=True,
        spacing=12,
        controls=[
            header,
            info_text,
            finalize_status_text,
            update_panel,
            editor_actions,
            ft.Container(
                expand=True,
                content=ft.Column(
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[md, editor],
                ),
            ),
        ],
    )

    page.add(content)

    def _poll() -> None:
        nonlocal last_content, last_mode, last_finalize_status
        while True:
            minutes_json = _read_json(minutes_json_path)
            status_json = _read_json(status_path)
            _update_buttons(minutes_json, status_json)
            finalize_summary = _finalize_status_summary(status_json)
            finalize_status_text.value = finalize_summary
            finalize_changed = finalize_summary != last_finalize_status
            last_finalize_status = finalize_summary

            if is_editing["value"]:
                editor_actions.visible = True
                editor.visible = True
                md.visible = False
                update_panel.visible = False
                update_panel.opacity = 0.0
                page.update()
                time.sleep(1.0)
                continue
            else:
                editor_actions.visible = False
                editor.visible = False
                md.visible = True

            if view_mode["value"] == "final":
                content, source_path = _resolve_final_markdown(minutes_json)
                info_text.value = "Showing final minutes"
                current_source["label"] = "final"
            else:
                content, source_path = _resolve_realtime_markdown(minutes_json)
                info_text.value = "Showing realtime minutes"
                current_source["label"] = "realtime"
            current_source["path"] = source_path

            if view_mode["value"] != "realtime":
                update_panel.visible = False
                update_panel.opacity = 0.0

            content_changed = content != last_content
            mode_changed = view_mode["value"] != last_mode

            if content_changed and view_mode["value"] == "realtime" and last_mode == "realtime" and last_content:
                inserted = _diff_inserted_lines(last_content, content)
                _show_update_panel(inserted)

            if mode_changed or content_changed:
                last_mode = view_mode["value"]
                last_content = content
                current_md["value"] = content
                md.value = content
                _update_mode_button_styles()
                page.update()
            elif finalize_changed:
                page.update()
            time.sleep(1.0)

    page.run_thread(_poll)


if __name__ == "__main__":
    ft.app(target=main)



