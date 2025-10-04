import os
import time
from typing import Iterator, Optional


def tail(path: str, follow: bool = True, sleep_s: float = 0.25, stop_event: Optional[object] = None) -> Iterator[str]:
    """Cross-platform tail with polling (no extra deps) plus rotation/truncation handling.

    Behavior:
    - Starts reading from end of file (like `tail -f`).
    - If file is truncated (size < last read position) or rotated (inode changes / file replaced),
      it reopens and continues from the new end (or beginning after truncate) without yielding
      duplicate lines.
    - If the file temporarily disappears (rotation gap), it waits until it reappears.
    """
    def _stat_or_none(p: str):
        try:
            return os.stat(p)
        except FileNotFoundError:
            return None

    st = _stat_or_none(path)
    # Open lazily; wait for file to appear if needed
    while st is None and follow:
        time.sleep(sleep_s)
        st = _stat_or_none(path)
    if st is None:  # not following, nothing to stream
        return

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        orig_ino = getattr(st, "st_ino", None)
        open_ctime = getattr(st, "st_ctime", None)
        while True:
            # External stop signal support (used in tests to avoid lingering threads / file locks)
            if stop_event is not None and getattr(stop_event, 'is_set', lambda: False)():
                break
            line = handle.readline()
            if line:
                yield line
                position = handle.tell()
                continue

            if not follow:
                break

            # Polling wait
            time.sleep(sleep_s)

            # Detect rotation / truncation
            st_now = _stat_or_none(path)
            if stop_event is not None and getattr(stop_event, 'is_set', lambda: False)():
                break
            if st_now is None:
                # File disappeared (likely rotation). Keep waiting for reappearance.
                continue
            truncated = st_now.st_size < position
            inode_changed = orig_ino is not None and getattr(st_now, "st_ino", None) != orig_ino
            ctime_changed = open_ctime is not None and getattr(st_now, "st_ctime", None) != open_ctime
            # Fallback rotation detection for platforms where st_ino may not change (e.g., Windows):
            # If we saw EOF, path stat size differs from the underlying handle file size, and the path size
            # is larger (indicating a new file with more content), treat as rotation.
            try:
                hstat = os.fstat(handle.fileno())
            except OSError:
                hstat = None
            fallback_rotation = False
            if not truncated and not inode_changed and hstat is not None:
                if st_now.st_size != getattr(hstat, 'st_size', st_now.st_size):
                    # Underlying handle size differs from current path size; if path is larger assume rotation.
                    if st_now.st_size > getattr(hstat, 'st_size', -1):
                        fallback_rotation = True

            if truncated or inode_changed or ctime_changed or fallback_rotation:
                try:
                    # Reopen file (new handle / reset position)
                    handle.close()
                finally:
                    handle = open(path, "r", encoding="utf-8", errors="replace")
                    # On truncation, start at beginning; on rotation, semantics: start at end of new file
                    if truncated:
                        handle.seek(0, os.SEEK_SET)
                        position = 0
                    else:  # rotation with new inode; mimic tail -F: start at end
                        handle.seek(0, os.SEEK_END)
                        position = handle.tell()
                    orig_ino = getattr(st_now, "st_ino", None)
                    open_ctime = getattr(st_now, "st_ctime", None)
                continue

            # No rotation; just seek back to last position so subsequent new lines read
            handle.seek(position)
