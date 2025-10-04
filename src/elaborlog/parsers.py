import json
import re
import sys
from typing import Optional, Tuple

# Very lightweight parser: try JSON logs first; fallback to naive parse
_LEVELS = {"CRITICAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG", "TRACE"}


def parse_line(line: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    Returns (timestamp, level, message_text).
    If JSON log with 'message' present, uses it; else naive extraction.
    """
    line = line.strip()
    if not line:
        return None, None, ""

    # Try JSON
    if line.startswith("{") and line.endswith("}"):
        try:
            obj = json.loads(line)
            ts = obj.get("timestamp") or obj.get("ts") or obj.get("@timestamp")
            level = (obj.get("level") or obj.get("severity") or obj.get("lvl") or "").upper()
            msg = obj.get("message") or obj.get("msg") or obj.get("log") or line
            level = level if level in _LEVELS else None
            return ts, level, str(msg)
        except Exception as exc:  # pragma: no cover - defensive parse fallback
            print(f"[elaborlog] warning: JSON parse failed: {exc}", file=sys.stderr)

    # Naive parse: [LEVEL] or LEVEL:
    match = re.search(r"\b(CRITICAL|ERROR|WARN|WARNING|INFO|DEBUG|TRACE)\b", line)
    level = match.group(1) if match else None

    # Timestamp heuristic (ISO-like)
    ts_match = re.search(r"\d{4}-\d{2}-\d{2}T?\s?\d{2}:\d{2}:\d{2}", line)
    ts = ts_match.group(0) if ts_match else None

    return ts, level, line
