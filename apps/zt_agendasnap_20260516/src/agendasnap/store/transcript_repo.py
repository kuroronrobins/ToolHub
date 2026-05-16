"""
Lightweight transcript repository.

Stores segments as JSON Lines on disk while keeping an in-memory list.

This class intentionally stays simple and synchronous.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from agendasnap.bus.events import TranscriptSegment


class TranscriptRepo:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._mem: List[TranscriptSegment] = []
        self.version: int = 0  # increments only when transcript content changes

    def append(self, segments: Iterable[TranscriptSegment]) -> None:
        seg_list = list(segments)
        if not seg_list:
            return

        with self.path.open("a", encoding="utf-8") as f:
            for seg in seg_list:
                f.write(
                    json.dumps(
                        {
                            "text": seg.text,
                            "start": seg.start,
                            "end": seg.end,
                            "source": seg.source,
                            "state": seg.state,
                            "confidence": seg.confidence,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        self._mem.extend(seg_list)
        self.version += 1

    @property
    def memory(self) -> List[TranscriptSegment]:
        # Return a copy to avoid accidental external mutation.
        return list(self._mem)

    def __len__(self) -> int:
        return len(self._mem)
