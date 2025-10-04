import math

import pytest

from elaborlog.parsers import parse_line
from elaborlog.score import InfoModel


def test_rare_lines_score_higher():
    model = InfoModel()
    common = ["INFO ok"] * 200
    rare = ["ERROR subsystem xyz failed code=999"]
    for line in common:
        _, _, message = parse_line(line)
        model.observe(message)
    _, _, rare_message = parse_line(rare[0])
    s_common = model.score("INFO ok").score
    s_rare = model.score(rare_message, level="ERROR").score
    assert s_rare > s_common


def test_novelty_matches_token_info_mapping():
    model = InfoModel()
    _, _, message = parse_line("INFO ok")
    model.observe(message)
    line_score = model.score(message)
    expected = 1 - math.exp(-line_score.token_info)
    assert line_score.novelty == pytest.approx(expected)


def test_snapshot_roundtrip(tmp_path):
    model = InfoModel()
    lines = [
        "INFO user login success user=123",
        "WARN user login delay user=124 latency=600ms",
        "ERROR user login failed user=125 code=42",
    ]
    for raw in lines:
        _, _, message = parse_line(raw)
        model.observe(message)

    before = model.score("ERROR user login failed user=125 code=42", level="ERROR")
    state_path = tmp_path / "state.json"
    model.save(state_path)

    restored = InfoModel.load(state_path)
    after = restored.score("ERROR user login failed user=125 code=42", level="ERROR")

    assert restored.token_counts == pytest.approx(model.token_counts)
    assert restored.template_counts == pytest.approx(model.template_counts)
    assert restored.total_tokens == pytest.approx(model.total_tokens)
    assert restored.total_templates == pytest.approx(model.total_templates)
    assert restored._seen_lines == model._seen_lines
    assert after.score == pytest.approx(before.score)
