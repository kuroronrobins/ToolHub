#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import time


def emit(event_type: str, message: str, progress: int | None = None) -> None:
    payload = {"type": event_type, "message": message}
    if progress is not None:
        payload["progress"] = progress
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> None:
    emit("status", "起動準備をしています", 10)
    time.sleep(0.5)
    emit("status", "データを確認しています", 45)
    time.sleep(0.5)
    print("通常のprint出力もログに保存されます。", flush=True)
    time.sleep(0.5)
    emit("success", "完了しました", 100)


if __name__ == "__main__":
    main()

