from __future__ import annotations

from pathlib import Path

from .models import ImportOptions, StudioContext
from .util import default_app_id_for_entry, display_name_from_app_id, output_dir_for_entry, resolve_existing_file, slugify_app_id


def create_context(options: ImportOptions, repo_root: Path) -> StudioContext:
    entry = resolve_existing_file(options.entry)
    app_id = slugify_app_id(options.app_id or default_app_id_for_entry(entry))
    name = options.name or display_name_from_app_id(app_id)
    source_root, source_root_origin = resolve_source_root(options.source_root, entry)
    source_root_warnings = source_scope_warnings(source_root, entry, repo_root.resolve(), source_root_origin)
    output_dir = output_dir_for_entry(entry, app_id).resolve()
    return StudioContext(
        repo_root=repo_root.resolve(),
        entry=entry,
        source_root=source_root,
        source_root_origin=source_root_origin,
        source_root_warnings=source_root_warnings,
        app_id=app_id,
        name=name,
        output_dir=output_dir,
        requested_build_mode=options.build_mode,
        build_mode=options.build_mode,
        version=options.version,
    )


def resolve_source_root(requested_source_root: Path | None, entry: Path) -> tuple[Path, str]:
    if requested_source_root is None or str(requested_source_root).strip() == "":
        return entry.parent.resolve(), "entry_parent"

    source_root = requested_source_root.expanduser().resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"source_root directory was not found: {source_root}")
    if is_filesystem_root(source_root):
        raise ValueError(f"source_root is too broad and unsafe: {source_root}")
    try:
        entry.resolve().relative_to(source_root)
    except ValueError as exc:
        raise ValueError(f"Entry file must be inside source_root. entry={entry}; source_root={source_root}") from exc
    return source_root, "explicit"


def source_scope_warnings(source_root: Path, entry: Path, repo_root: Path, origin: str) -> list[str]:
    warnings: list[str] = []
    if source_root.resolve() == repo_root.resolve():
        warnings.append("source_root is the ToolHub repository root; this is usually too broad for an app registration.")
    if source_root.name.lower() in {"rd", "documents", "downloads", "desktop"}:
        warnings.append("source_root looks like a broad workspace or user folder; choose the app project directory when possible.")
    try:
        entry_relative = entry.resolve().relative_to(source_root.resolve())
        if len(entry_relative.parts) > 6:
            warnings.append("entry is deeply nested under source_root; confirm unrelated parent folders are not being included.")
    except ValueError:
        pass
    if origin == "entry_parent" and (source_root / ".git").is_dir():
        warnings.append("auto source_root contains a .git directory; use --source-root if only a subdirectory should be packaged.")
    return warnings


def is_filesystem_root(path: Path) -> bool:
    resolved = path.resolve()
    return resolved == resolved.parent

