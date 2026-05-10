#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import time


def emit(event_type: str, message: str, progress: int | None = None) -> None:
    payload: dict[str, object] = {"type": event_type, "message": message}
    if progress is not None:
        payload["progress"] = progress
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    emit("status", "データを確認しています", 40)
    time.sleep(0.1)
    emit("status", "処理を実行しています", 75)
    time.sleep(0.1)
    emit("success", "完了しました", 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

