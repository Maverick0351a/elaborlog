import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
    from elaborlog.service import build_app  # type: ignore
    FASTAPI_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency missing
    FASTAPI_AVAILABLE = False


pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi extra not installed")


def _client():
    app = build_app()
    return TestClient(app)


def test_observe_and_stats_increment():
    client = _client()
    r = client.get("/stats")
    assert r.status_code == 200
    initial = r.json()

    line = "2024-01-01T00:00:00Z INFO First test line"
    for _ in range(3):
        orr = client.post("/observe", json={"line": line})
        assert orr.status_code == 200

    r2 = client.get("/stats")
    assert r2.status_code == 200
    after = r2.json()

    # tokens/templates should be > 0 and totals advanced
    assert after["tokens"] >= initial["tokens"]
    assert after["templates"] >= initial["templates"]
    assert after["total_tokens"] > initial["total_tokens"]
    assert after["total_templates"] > initial["total_templates"]
    assert after["seen_lines"] == initial["seen_lines"] + 3


def test_score_endpoint_returns_expected_fields():
    client = _client()
    line = "2024-01-01T00:00:00Z ERROR Something happened in module xyz"  # ensure level parsing

    # Observe once so model has template
    client.post("/observe", json={"line": line})

    resp = client.post("/score", json={"line": line, "level": "ERROR"})
    assert resp.status_code == 200
    data = resp.json()

    expected_keys = {"score", "novelty", "token_info", "template_info", "level_bonus", "template", "tokens"}
    assert expected_keys == set(data.keys())

    # Basic sanity checks on numeric ranges
    assert 0.0 <= data["novelty"] <= 1.0
    # Score is weighted sum of self-information; allow generous bound.
    assert 0.0 <= data["score"] < 20.0
    assert isinstance(data["tokens"], list) and data["tokens"], "tokens should be a non-empty list"


def test_healthz():
    client = _client()
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
