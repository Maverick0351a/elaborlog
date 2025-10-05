"""Alert sink abstractions.

Initial quick-win refactor: provide a pluggable interface for emitting alerts.
Currently used only by tail for JSONL writes; can extend later to webhook, Slack, etc.
"""
from __future__ import annotations
from typing import Protocol, Dict, Any, List

class AlertSink(Protocol):  # pragma: no cover - simple protocol
    def emit(self, alert: Dict[str, Any]) -> None: ...  # noqa: D401,E701 - protocol stub
    def close(self) -> None: ...

class JsonlSink:
    def __init__(self, path: str, all_token_contributors: bool = False) -> None:
        self.path = path
        self.all_token_contributors = all_token_contributors
        self._fh = open(path, "a", encoding="utf-8")

    def emit(self, alert: Dict[str, Any]) -> None:
        import json
        self._fh.write(json.dumps(alert) + "\n")
        self._fh.flush()

    def close(self) -> None:  # pragma: no cover - trivial
        try:
            self._fh.close()
        except Exception:
            pass

class MultiSink:
    def __init__(self, sinks: List[AlertSink]):
        self._sinks = sinks

    def emit(self, alert: Dict[str, Any]) -> None:
        for s in self._sinks:
            try:
                s.emit(alert)
            except Exception:
                # Best-effort; individual sink failure should not cascade.
                pass

    def close(self) -> None:  # pragma: no cover
        for s in self._sinks:
            try:
                s.close()
            except Exception:
                pass

__all__ = ["AlertSink", "JsonlSink", "MultiSink"]
