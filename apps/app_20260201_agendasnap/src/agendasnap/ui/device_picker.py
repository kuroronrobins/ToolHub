"""Device picker UI and label helpers."""
from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import Callable

import flet as ft

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceChoice:
    source: str
    value: str
    label: str
    tooltip: str
    index: int | None = None


def short_device_label(label: str | None, *, max_chars: int = 28) -> str:
    text = str(label or "").strip()
    if not text:
        return "利用不可"
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1] + "…"


def device_tooltip(label: str | None, *, index: int | None = None, source_label: str | None = None) -> str:
    text = str(label or "").strip() or "利用不可"
    parts = []
    if source_label:
        parts.append(source_label)
    if index is not None:
        parts.append(f"index {index}")
    parts.append(text)
    return " / ".join(parts)


def build_device_choices(
    *,
    source: str,
    options: list[tuple[int, str]],
    default_name: str | None,
) -> list[DeviceChoice]:
    source_label = "SYSTEM" if source == "sys" else "MIC"
    choices = [
        DeviceChoice(
            source=source,
            value="auto",
            label=f"Default / Auto ({default_name})" if default_name else "Default / Auto",
            tooltip=device_tooltip(default_name or "Default / Auto", source_label=source_label),
        ),
        DeviceChoice(
            source=source,
            value="off",
            label="OFF",
            tooltip=f"{source_label} input OFF",
        ),
    ]
    for idx, name in options:
        choices.append(
            DeviceChoice(
                source=source,
                value=str(idx),
                label=f"[{idx}] {name}",
                tooltip=device_tooltip(name, index=idx, source_label=source_label),
                index=idx,
            )
        )
    return choices


def _page_update(page: ft.Page) -> None:
    with contextlib.suppress(Exception):
        page.update()


def _open_dialog_compat(page: ft.Page, dialog: ft.AlertDialog) -> None:
    """Open an AlertDialog across Flet versions."""
    with contextlib.suppress(Exception):
        dialog.open = True

    show_dialog = getattr(page, "show_dialog", None)
    if callable(show_dialog):
        try:
            show_dialog(dialog)
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("page.show_dialog failed; falling back: %s", exc)

    open_control = getattr(page, "open", None)
    if callable(open_control):
        try:
            open_control(dialog)
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("page.open failed; falling back: %s", exc)

    page.dialog = dialog
    dialog.open = True
    _page_update(page)


def _close_dialog_compat(page: ft.Page, dialog: ft.AlertDialog) -> None:
    """Close an AlertDialog across Flet versions."""
    pop_dialog = getattr(page, "pop_dialog", None)
    if callable(pop_dialog):
        try:
            pop_dialog()
            with contextlib.suppress(Exception):
                dialog.open = False
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("page.pop_dialog failed; falling back: %s", exc)

    close_control = getattr(page, "close", None)
    if callable(close_control):
        try:
            close_control(dialog)
            with contextlib.suppress(Exception):
                dialog.open = False
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("page.close failed; falling back: %s", exc)

    dialog.open = False
    _page_update(page)


class DevicePickerDialog:
    """Searchable source/device picker for long Windows device names."""

    def __init__(
        self,
        *,
        page: ft.Page,
        source: str,
        title: str,
        selected_value: str,
        choices_provider: Callable[[], list[DeviceChoice]],
        on_select: Callable[[str], None],
    ) -> None:
        self.page = page
        self.source = source
        self.title = title
        self.selected_value = selected_value
        self.choices_provider = choices_provider
        self.on_select = on_select
        self.query = ""
        self.error_text = ft.Text("", size=12, color="#B91C1C", visible=False)
        self.list_view = ft.ListView(expand=True, spacing=2, padding=0)
        self.search = ft.TextField(
            hint_text="検索",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_search,
            autofocus=True,
        )
        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Container(
                width=680,
                height=500,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.Container(expand=True, content=self.search),
                                ft.IconButton(
                                    icon=ft.Icons.REFRESH,
                                    tooltip="デバイス一覧を更新",
                                    on_click=self._on_refresh,
                                ),
                            ],
                        ),
                        self.error_text,
                        ft.Container(expand=True, content=self.list_view),
                    ],
                ),
            ),
            actions=[ft.TextButton("閉じる", on_click=self.close)],
        )

    def open(self) -> None:
        self._refresh()
        _open_dialog_compat(self.page, self.dialog)

    def close(self, _e: ft.ControlEvent | None = None) -> None:
        _close_dialog_compat(self.page, self.dialog)

    def _on_search(self, e: ft.ControlEvent) -> None:
        self.query = str(e.control.value or "").strip().lower()
        self._refresh()
        self.page.update()

    def _on_refresh(self, _e: ft.ControlEvent) -> None:
        self._refresh()
        self.page.update()

    def _refresh(self) -> None:
        try:
            choices = self.choices_provider()
            self.error_text.visible = False
            self.error_text.value = ""
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load device choices")
            self.error_text.value = f"デバイス一覧を取得できません: {exc}"
            self.error_text.visible = True
            choices = []
        query = self.query
        if query:
            choices = [
                choice
                for choice in choices
                if query in choice.label.lower() or query in choice.tooltip.lower()
            ]
        self.list_view.controls = [self._build_row(choice) for choice in choices]

    def _build_row(self, choice: DeviceChoice) -> ft.Control:
        checked = choice.value == self.selected_value

        def _pick(_e: ft.ControlEvent, value: str = choice.value) -> None:
            try:
                self.on_select(value)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Device selection failed: %s", value)
                self.error_text.value = f"入力を切り替えられません: {exc}"
                self.error_text.visible = True
                _page_update(self.page)
                return
            self.close()

        icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE if checked else ft.Icons.RADIO_BUTTON_UNCHECKED,
            color="#111111" if checked else "#9CA3AF",
        )
        label = ft.Text(
            choice.label,
            selectable=True,
            tooltip=choice.tooltip,
            max_lines=2,
            overflow=ft.TextOverflow.VISIBLE,
        )
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            border_radius=6,
            bgcolor="#F3F4F6" if checked else "#FFFFFF",
            on_click=_pick,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    icon,
                    ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            label,
                            ft.Text(choice.tooltip, size=12, color="#6B7280", selectable=True),
                        ],
                    ),
                ],
            ),
        )
