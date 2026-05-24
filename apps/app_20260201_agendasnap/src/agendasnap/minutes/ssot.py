"""minutes.json SSOT utilities."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agendasnap.minutes.schema import MinutesDocument, MinutesMeta, MinutesHeader
from agendasnap.store.atomic import write_text_atomic


def load_minutes_json(path: Path) -> MinutesDocument:
    if not path.exists():
        return MinutesDocument()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return MinutesDocument()
    return MinutesDocument.from_dict(data or {})


def save_minutes_json_atomic(path: Path, doc: MinutesDocument) -> None:
    doc.meta.generated_at = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(doc.to_dict(), ensure_ascii=False, indent=2)
    write_text_atomic(path, payload, encoding="utf-8")


def init_minutes_doc(*, model: str | None, mode: str, prompt_version: str | None) -> MinutesDocument:
    doc = MinutesDocument()
    doc.meta = MinutesMeta(
        version=1,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model=model,
        mode=mode,
        last_segment_index=0,
        prompt_version=prompt_version,
    )
    doc.header = MinutesHeader()
    return doc
