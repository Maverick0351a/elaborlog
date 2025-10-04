from elaborlog.score import InfoModel
from elaborlog.config import ScoringConfig


def test_line_length_truncation_and_token_cap():
    cfg = ScoringConfig(max_line_length=50, max_tokens_per_line=5)
    m = InfoModel(cfg)
    long_line = "INFO " + " ".join([f"tok{i}" for i in range(30)])
    m.observe(long_line)
    # After observe, counters should reflect truncation events (at least one of them)
    assert m.lines_truncated == 1  # raw line should be truncated
    assert m.lines_token_truncated == 1  # token list capped
    assert m.lines_dropped == 0  # we did not implement drop heuristic

    # Ensure only up to token cap (plus maybe 'info') tokens stored
    assert len(m.token_counts) <= cfg.max_tokens_per_line + 1


def test_snapshot_restores_guardrail_counters(tmp_path):
    cfg = ScoringConfig(max_line_length=20, max_tokens_per_line=3)
    m = InfoModel(cfg)
    for _ in range(3):
        m.observe("INFO x y z q r s t u v")
    snap_path = tmp_path / "guard_state.json"
    m.save(snap_path)
    restored = InfoModel.load(snap_path)
    assert restored.lines_truncated == m.lines_truncated
    assert restored.lines_token_truncated == m.lines_token_truncated
    assert restored.lines_dropped == m.lines_dropped
