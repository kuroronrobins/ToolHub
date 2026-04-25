from __future__ import annotations

from pathlib import Path

from .models import ImportOptions, StudioContext
from .util import default_app_id_for_entry, display_name_from_app_id, output_dir_for_entry, resolve_existing_file, slugify_app_id


def create_context(options: ImportOptions, repo_root: Path) -> StudioContext:
    entry = resolve_existing_file(options.entry)
    app_id = slugify_app_id(options.app_id or default_app_id_for_entry(entry))
    name = options.name or display_name_from_app_id(app_id)
    source_root = entry.parent.resolve()
    output_dir = output_dir_for_entry(entry, app_id).resolve()
    return StudioContext(
        repo_root=repo_root.resolve(),
        entry=entry,
        source_root=source_root,
        app_id=app_id,
        name=name,
        output_dir=output_dir,
        requested_build_mode=options.build_mode,
        build_mode=options.build_mode,
        version=options.version,
    )

