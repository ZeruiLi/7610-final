from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from fastapi.responses import FileResponse, Response
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration
import requests
from models import Candidate, Place, PreferenceSpec
from services.candidate_search import search_candidates
from services.preferences import parse_preferences
from services.ranking import rank_candidates
from services.rerank import apply_rerank
from services.report import build_report
from services.details import fetch_details
from services.reasoner import build_reason


app = FastAPI(title="Restaurant Recommender (MVP)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve minimal frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount Flutter web app only when built
if os.path.isdir(os.path.join(os.path.dirname(__file__), "static", "app")):
    app.mount("/app", StaticFiles(directory="static/app", html=True), name="app")

@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")

@app.get("/favicon.ico")
def favicon() -> Response:
    # Avoid noisy 404 in logs if browser asks for favicon
    return Response(status_code=204)


def _to_str_list(value: Any) -> list[str]:
    """Normalize mixed list/object to list[str] for API schema.

    Accepts list[str|dict|any] | dict | str | None and returns list[str].
    Dicts are converted by joining key-value pairs or values.
    """
    out: list[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        s = value.strip()
        if s:
            out.append(s)
        return out
    if isinstance(value, dict):
        # prefer 'reason' if exists, else join values
        if "reason" in value and isinstance(value["reason"], str):
            out.append(value["reason"].strip())
        else:
            joined = " ".join(str(v) for v in value.values())
            if joined.strip():
                out.append(joined.strip())
        return out
    if isinstance(value, list):
        for item in value:
            out.extend(_to_str_list(item))
        # dedupe while preserving order
        seen = set()
        deduped: list[str] = []
        for s in out:
            if s not in seen:
                seen.add(s)
                deduped.append(s)
        return deduped
    # fallback to str
    s = str(value).strip()
    if s:
        out.append(s)
    return out


class RecommendRequest(BaseModel):
    query: str = Field(..., description="Natural-language dining request")
    session_id: Optional[str] = Field(None, description="Session ID for conversation history")
    limit: int = Field(8, description="Number of results to enrich and return details for")


class PlacePayload(BaseModel):
    name: str
    address: Optional[str]
    lon: float
    lat: float
    website: Optional[str] = None
    opening_hours: Optional[str] = None
    datasource_url: Optional[str] = None
    tags: List[str] = []
    rating: Optional[float] = None


class CandidatePayload(BaseModel):
    place: PlacePayload
    score: float
    reason: str
    pros: List[str] = []
    cons: List[str] = []
    # v2 additions
    highlights: List[str] = []
    signature_dishes: List[str] = []
    why_matched: List[str] = []
    risks: List[str] = []
    detail_sources: List[Dict[str, Any]] = []
    match_cuisine: bool = False
    match_ambience: bool = False
    match_budget: bool = False
    match_distance: bool = False
    match_popularity: bool = False
    primary_tags: List[str] = []
    reliability_score: float = 0.0
    distance_km: float = 0.0
    distance_miles: float = 0.0
    source_hits: int = 0
    source_trust_score: float = 0.0
    is_open_ok: bool = True
    violated_constraints: List[str] = []


class RecommendResponse(BaseModel):
    recommendations_markdown: str
    candidates: List[CandidatePayload]
    preferences: Dict[str, Any]
    bbox: Tuple[float, float, float, float]


@app.get("/healthz")
def healthz() -> dict:
    cfg = Configuration.from_env()
    logger.info("cfg: {}", cfg.log_summary())
    return {"status": "ok"}


@app.get("/health/geo")
def health_geo() -> dict:
    cfg = Configuration.from_env()
    try:
        cfg.require_geoapify()
        url = (
            f"{cfg.geoapify_base_url.rstrip('/')}/v1/geocode/search"
            f"?text=Seattle&limit=1&lang=en&apiKey={cfg.geoapify_api_key}"
        )
        r = requests.get(url, timeout=cfg.geoapify_timeout)
        ok = r.ok
    except Exception:
        ok = False
    return {"ok": ok}


@app.get("/health/llm")
def health_llm() -> dict:
    cfg = Configuration.from_env()
    provider = (cfg.llm_provider or "").lower()
    ok = False
    detail = None
    try:
        if provider == "ollama":
            base = cfg.ollama_base_url.rstrip("/")
            url = f"{base}/api/tags"
            r = requests.get(url, timeout=5)
            ok = r.ok
            if r.ok:
                data = r.json()
                detail = data.get("models", [])
        else:
            # If llm_base_url present, try /models (OpenAI-compatible)
            if cfg.llm_base_url:
                url = f"{cfg.llm_base_url.rstrip('/')}/models"
                r = requests.get(url, timeout=5)
                ok = r.ok
    except Exception as exc:
        ok = False
        detail = str(exc)
    return {"ok": ok, "provider": provider or "unset", "detail": detail}


@app.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest) -> RecommendResponse:
    try:
        cfg = Configuration.from_env()
        cfg.require_geoapify()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        # Session handling
        from services.session import session_manager
        history = session_manager.get_history(req.session_id) if req.session_id else None

        spec: PreferenceSpec = parse_preferences(cfg, req.query, history=history)
        if not spec.city:
            raise ValueError("Unable to parse a city from the request. Please include a US city or metro area.")

        places, bbox = search_candidates(cfg, spec)
        center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
        ranked = rank_candidates(spec, places, bbox_center=center)
        ranked = apply_rerank(cfg, spec, ranked)

    # v2: enrich top-K with details and reason
        top_k = min(req.limit, len(ranked))
        
        import asyncio
        from services.details import fetch_details_async

        async def process_candidate(c):
            ctx = await fetch_details_async(c.place, lang=spec.lang or cfg.lang_default)
            # Run reasoner in thread to avoid blocking
            reason = await asyncio.to_thread(build_reason, cfg, spec, c.place, ctx)
            
            c.highlights = _to_str_list(reason.get("highlights"))
            c.signature_dishes = _to_str_list(reason.get("signature_dishes"))
            c.why_matched = _to_str_list(reason.get("why_matched"))
            c.risks = _to_str_list(reason.get("risks"))
            c.detail_sources = list(ctx.sources or [])
            c.source_hits = ctx.hits
            c.source_trust_score = ctx.trust_score

        # Run in parallel
        await asyncio.gather(*(process_candidate(c) for c in ranked[:top_k]))

        md = build_report(spec, ranked, bbox)
        
        # Save turn
        if req.session_id:
            session_manager.add_turn(req.session_id, req.query, md)

        avg_trust = sum(c.source_trust_score for c in ranked[:top_k]) / max(top_k, 1) if top_k else 0.0
        distances = [c.distance_miles for c in ranked[:top_k] if c.distance_miles]
        median_distance = statistics.median(distances) if distances else 0.0
        logger.info(
            "recommendation city=%s area=%s radius_km=%.2f candidates=%d avg_trust=%.2f median_distance_miles=%.2f",
            spec.city,
            spec.area,
            spec.distance_km,
            len(ranked),
            avg_trust,
            median_distance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("recommendation failed: {}", exc)
        raise HTTPException(status_code=500, detail="internal error")

    def to_payload(p: Place) -> PlacePayload:
        return PlacePayload(
            name=p.name,
            address=p.address,
            lon=p.lon,
            lat=p.lat,
            website=p.website,
            opening_hours=p.opening_hours,
            datasource_url=p.datasource_url,
            tags=p.tags,
            rating=p.rating,
        )

    cands = [
        CandidatePayload(
            place=to_payload(c.place),
            score=c.score,
            reason=c.reason,
            pros=c.pros,
            cons=c.cons,
            highlights=c.highlights,
            signature_dishes=c.signature_dishes,
            why_matched=c.why_matched,
            risks=c.risks,
            detail_sources=c.detail_sources,
            match_cuisine=c.match_cuisine,
            match_ambience=c.match_ambience,
            match_budget=c.match_budget,
            match_distance=c.match_distance,
            match_popularity=c.match_popularity,
            primary_tags=c.primary_tags,
            reliability_score=c.reliability_score,
            distance_km=c.distance_km,
            distance_miles=c.distance_miles,
            source_hits=c.source_hits,
            source_trust_score=c.source_trust_score,
            is_open_ok=c.is_open_ok,
            violated_constraints=c.violated_constraints,
        )
        for c in ranked
    ]

    return RecommendResponse(
        recommendations_markdown=md,
        candidates=cands,
        preferences=spec.__dict__,
        bbox=bbox,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)
