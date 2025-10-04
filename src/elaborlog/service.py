"""Optional FastAPI service exposing Elaborlog scoring as HTTP endpoints.

Install with `pip install elaborlog[server]` to enable.
This keeps the core library dependency-light.
"""
from __future__ import annotations

import threading
from typing import Optional  # use built-in generics for list/dict

try:  # pragma: no cover - optional dependency
    from fastapi import FastAPI
    from pydantic import BaseModel
except Exception as exc:  # noqa: BLE001
    raise RuntimeError(
        "FastAPI not installed. Install with `pip install elaborlog[server]` to use the service."  # noqa: E501
    ) from exc

from .parsers import parse_line
from .score import InfoModel
from .metrics import model_metrics


class ObserveRequest(BaseModel):
    line: str
    level: Optional[str] = None
    timestamp: Optional[str] = None  # accepted but not used yet


class ScoreRequest(BaseModel):
    line: str
    level: Optional[str] = None


class ScoreResponse(BaseModel):
    score: float
    novelty: float
    token_info: float
    template_info: float
    level_bonus: float
    template: str
    tokens: List[str]


class StatsResponse(BaseModel):
    tokens: int
    templates: int
    total_tokens: float
    total_templates: float
    seen_lines: int


def build_app(model: Optional[InfoModel] = None) -> FastAPI:
    model = model or InfoModel()
    app = FastAPI(title="Elaborlog Service", version="0.1.0")
    # Single lock protecting all mutable model state; FastAPI handlers are lightweight so
    # coarse-grained locking keeps thread-safety simple without visible contention.
    lock = threading.Lock()

    @app.get("/healthz")
    def health() -> dict[str, str]:  # pragma: no cover - trivial
        return {"status": "ok"}

    @app.post("/observe")
    def observe(req: ObserveRequest) -> dict[str, str]:
        with lock:
            _, _, msg = parse_line(req.line)
            model.observe(msg)
        return {"status": "observed"}

    @app.post("/score", response_model=ScoreResponse)
    def score(req: ScoreRequest) -> ScoreResponse:
        _, _, msg = parse_line(req.line)
        with lock:
            sc = model.score(msg, level=req.level)
        return ScoreResponse(
            score=sc.score,
            novelty=sc.novelty,
            token_info=sc.token_info,
            template_info=sc.template_info,
            level_bonus=sc.level_bonus,
            template=sc.tpl,
            tokens=sc.toks,
        )

    @app.get("/stats", response_model=StatsResponse)
    def stats() -> StatsResponse:
        with lock:
            return StatsResponse(
                tokens=len(model.token_counts),
                templates=len(model.template_counts),
                total_tokens=model.total_tokens,
                total_templates=model.total_templates,
                seen_lines=model._seen_lines,
            )

    @app.get("/metrics")
    def metrics() -> dict[str, object]:  # pragma: no cover - covered by dedicated test
        with lock:
            return model_metrics(model)

    return app


__all__ = ["build_app"]
