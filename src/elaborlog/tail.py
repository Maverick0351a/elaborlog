import os
import time
from typing import Iterator


def tail(path: str, follow: bool = True, sleep_s: float = 0.25) -> Iterator[str]:
    """Cross-platform tail with polling (no extra deps)."""
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        while True:
            line = handle.readline()
            if line:
                yield line
                position = handle.tell()
            elif follow:
                time.sleep(sleep_s)
                handle.seek(position)
            else:
                break
