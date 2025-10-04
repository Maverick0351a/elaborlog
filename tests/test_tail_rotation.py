import os
import time
import threading
import tempfile
from pathlib import Path
from elaborlog.tail import tail


def wait_for(predicate, timeout=5.0, interval=0.02, msg="condition not met"):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(interval)
    raise AssertionError(msg)


def test_tail_truncate_and_rotation():
    """Ensure tail yields new lines after truncation and only appended lines after rotation.

    Uses a background thread consuming the generator with explicit closure to avoid file locking.
    """
    import os
    import time
    import threading
    import tempfile
    from pathlib import Path
    from elaborlog.tail import tail


    def test_tail_truncate_and_rotation():
        """Test tail behavior for truncation (all platforms) and rotation (POSIX only)."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "app.log"
            p.write_text("one\n", encoding="utf-8")
            collected: list[str] = []
            stop = threading.Event()
            started = threading.Event()

            def consumer():
                for line in tail(str(p), follow=True, sleep_s=0.01, stop_event=stop):
                    collected.append(line.rstrip("\n"))
                    if stop.is_set():
                        break

            t = threading.Thread(target=consumer, daemon=True)
            t.start()
            started.set()  # tail starts immediately
            time.sleep(0.05)

            try:
                # Append two lines
                with p.open("a", encoding="utf-8") as h:
                    h.write("two\n")
                    h.write("three\n")
                deadline = time.time() + 2.0
                while time.time() < deadline and ("two" not in collected or "three" not in collected):
                    time.sleep(0.01)
                assert "two" in collected and "three" in collected, f"Missing two/three: {collected}"

                # Truncate and write new line
                p.write_text("", encoding="utf-8")
                with p.open("a", encoding="utf-8") as h:
                    h.write("fresh\n")
                deadline = time.time() + 2.0
                while time.time() < deadline and "fresh" not in collected:
                    time.sleep(0.01)
                assert "fresh" in collected, f"fresh not seen after truncation: {collected}"

                if os.name != "nt":
                    rotated = Path(d) / "app.log.1"
                    os.replace(p, rotated)
                    p.write_text("newA\nnewB\n", encoding="utf-8")
                    with p.open("a", encoding="utf-8") as h:
                        h.write("newC\n")
                    prev_len = len(collected)
                    deadline = time.time() + 2.0
                    while time.time() < deadline:
                        if len(collected) > prev_len and collected[-1] == "newC":
                            break
                        time.sleep(0.01)
                    assert len(collected) > prev_len and collected[-1] == "newC", (
                        f"newC not observed after rotation; delta={collected[prev_len:]}"
                    )
                    assert collected[prev_len:] == ["newC"], f"Unexpected post-rotation lines: {collected[prev_len:]}"
            finally:
                stop.set()
                # Allow loop to notice stop
                time.sleep(0.05)
                t.join(timeout=1.0)
