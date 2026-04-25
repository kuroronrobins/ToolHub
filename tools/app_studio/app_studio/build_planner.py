from __future__ import annotations

from pathlib import Path

from .models import BuildPlan, SourceInventory, StudioContext


COMPLEX_IMPORTS = {
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "pyaudio",
    "sounddevice",
    "soundfile",
    "whisper",
    "torch",
    "cv2",
    "numpy",
    "pandas",
    "playwright",
}
ASSET_SUFFIXES = {".dll", ".so", ".dylib", ".wav", ".mp3", ".m4a", ".onnx", ".bin"}


def make_build_plan(context: StudioContext, inventory: SourceInventory) -> BuildPlan:
    requested = context.requested_build_mode
    mode, reasons = select_build_mode(context, inventory) if requested == "auto" else (requested, [f"BuildMode was explicitly set to {requested}."])

    if mode == "existing-exe":
        runner = "exe"
        entry = f"bin/{context.entry.name}"
        required_runtime = None
    elif mode == "frozen-folder":
        runner = "exe"
        entry = f"bin/{context.app_id}/{context.app_id}.exe"
        required_runtime = None
    else:
        runner = "python_app_env"
        entry = f"src/{context.entry_relative.as_posix()}"
        required_runtime = "python-embedded-toolhub-001"

    warnings: list[str] = []
    if mode == "frozen-folder":
        warnings.append("Frozen-folder uses PyInstaller --onedir or an equivalent folder build.")
        warnings.append("Use PyInstaller --onedir or equivalent. --onefile is not the ToolHub standard.")
    if mode == "existing-exe":
        warnings.append("Existing executable folders are copied as folder/exe style assets.")

    return BuildPlan(mode=mode, runner=runner, entry=entry, required_runtime=required_runtime, reasons=reasons, warnings=warnings)


def select_build_mode(context: StudioContext, inventory: SourceInventory) -> tuple[str, list[str]]:
    if context.entry.suffix.lower() == ".exe":
        return "existing-exe", ["Entry is already an executable."]

    included = inventory.included_files
    python_files = [path for path in included if path.suffix.lower() == ".py"]
    asset_files = [path for path in included if has_asset_or_binary_signal(path)]
    complex_imports = sorted(set(inventory.import_roots) & COMPLEX_IMPORTS)

    if len(python_files) > 10:
        return "frozen-folder", [f"Many Python modules were detected: {len(python_files)}."]
    if asset_files:
        return "frozen-folder", ["Assets, binary files, audio files, or config folders were detected."]
    if complex_imports:
        return "frozen-folder", ["Complex dependencies were detected: " + ", ".join(complex_imports)]

    return "app-env", ["Simple Python entry and dependency profile."]


def has_asset_or_binary_signal(path: Path) -> bool:
    lower_parts = {part.lower() for part in path.parts}
    if lower_parts & {"assets", "templates", "static", "config", "config.default"}:
        return True
    return path.suffix.lower() in ASSET_SUFFIXES


def build_plan_markdown(plan: BuildPlan, context: StudioContext) -> str:
    lines = [
        "# Build Plan",
        "",
        f"- app_id: `{context.app_id}`",
        f"- name: `{context.name}`",
        f"- selected_mode: `{plan.mode}`",
        f"- runner: `{plan.runner}`",
        f"- entry: `{plan.entry}`",
        "",
        "## Reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in plan.reasons)
    if plan.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in plan.warnings)
    if plan.mode == "app-env":
        lines.extend(
            [
                "",
                "## app_env Layout",
                "",
                f"- Runtime: `runtime/app_envs/{context.app_id}/Scripts/python.exe`",
                "- Fallback runtime: `runtime/python/python.exe`",
                "- User PATH Python is not required for the imported app.",
            ]
        )
    elif plan.mode == "frozen-folder":
        lines.extend(
            [
                "",
                "## frozen-folder Notes",
                "",
                "- Build with a folder-based frozen output such as PyInstaller `--onedir`.",
                "- Do not use `--onefile` as the standard packaging path.",
                f"- Expected executable after future build: `{plan.entry}`",
            ]
        )
    else:
        lines.extend(["", "## existing-exe Notes", "", "- Copy the executable and its sibling runtime files under `bin/`."])
    return "\n".join(lines) + "\n"
