from __future__ import annotations

import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolhub_runner.event_protocol import parse_event_line


class EventProtocolTests(unittest.TestCase):
    def test_json_status_event(self) -> None:
        event = parse_event_line('{"type":"status","message":"確認中","progress":60}')
        self.assertEqual(event.type, "status")
        self.assertEqual(event.message, "確認中")
        self.assertEqual(event.progress, 60)

    def test_invalid_json_becomes_output(self) -> None:
        event = parse_event_line("通常のprint出力")
        self.assertEqual(event.type, "output")
        self.assertEqual(event.message, "通常のprint出力")

    def test_unknown_type_becomes_output(self) -> None:
        event = parse_event_line('{"type":"custom","message":"hello"}')
        self.assertEqual(event.type, "output")
        self.assertEqual(event.message, "hello")


if __name__ == "__main__":
    unittest.main()

