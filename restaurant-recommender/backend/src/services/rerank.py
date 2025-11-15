from __future__ import annotations

import logging
from typing import List

from config import Configuration
from models import Candidate, PreferenceSpec

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import CrossEncoder
except ImportError:  # pragma: no cover
    CrossEncoder = None  # type: ignore[assignment]


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: CrossEncoder | None = None  # type: ignore[name-defined]

    def _ensure_model(self) -> None:
        if self._model is None:
            if CrossEncoder is None:
                raise RuntimeError("sentence-transformers is not installed")
            self._model = CrossEncoder(self.model_name)  # type: ignore[call-arg]

    def score(self, query: str, documents: List[str]) -> List[float]:
        self._ensure_model()
        assert self._model is not None
        pairs = [[query, doc] for doc in documents]
        scores = self._model.predict(pairs)  # type: ignore[call-arg]
        return scores.tolist() if hasattr(scores, "tolist") else list(scores)


_singleton: CrossEncoderReranker | None = None


def _normalize(scores: List[float]) -> List[float]:
    if not scores:
        return scores
    min_v = min(scores)
    max_v = max(scores)
    if max_v - min_v < 1e-6:
        return [0.5 for _ in scores]
    return [(s - min_v) / (max_v - min_v) for s in scores]


def _build_query(spec: PreferenceSpec) -> str:
    parts: list[str] = []
    if spec.city:
        parts.append(f"Best restaurants in {spec.city}")
    if spec.area:
        parts.append(f"Neighborhood: {spec.area}")
    if spec.cuisines:
        parts.append(f"Cuisine: {', '.join(spec.cuisines)}")
    if spec.ambiance:
        parts.append(f"Ambience: {', '.join(spec.ambiance)}")
    if spec.budget_per_capita:
        parts.append(f"Budget ${spec.budget_per_capita:.0f} per person")
    return " | ".join(parts)


def _build_document(candidate: Candidate) -> str:
    place = candidate.place
    tags = candidate.primary_tags or [t for t in place.tags if t]
    snippets = [
        place.name,
        place.address or "",
        ", ".join(tags),
        "; ".join(candidate.pros) or candidate.reason,
    ]
    return " | ".join(filter(None, snippets))


def apply_rerank(cfg: Configuration, spec: PreferenceSpec, candidates: List[Candidate]) -> List[Candidate]:
    if not cfg.rerank_enabled or not candidates:
        return candidates

    top_n = max(1, min(cfg.rerank_top_n, len(candidates)))
    subset = candidates[:top_n]
    query = _build_query(spec)
    documents = [_build_document(c) for c in subset]

    global _singleton
    if _singleton is None or _singleton.model_name != cfg.rerank_model:
        try:
            _singleton = CrossEncoderReranker(cfg.rerank_model)
        except RuntimeError as exc:  # pragma: no cover - dependency missing
            logger.warning("Rerank disabled: %s", exc)
            cfg.rerank_enabled = False
            return candidates

    try:
        scores = _singleton.score(query, documents)
    except Exception as exc:  # pragma: no cover
        logger.warning("Rerank failed: %s", exc)
        return candidates

    normalized = _normalize(scores)
    weight = max(0.0, min(cfg.rerank_weight, 1.0))

    for candidate, rerank_score in zip(subset, normalized):
        candidate.score = float((1 - weight) * candidate.score + weight * rerank_score)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
