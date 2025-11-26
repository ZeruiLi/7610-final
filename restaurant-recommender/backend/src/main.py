from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from fastapi.responses import FileResponse, Response, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration
import requests
import time
from models import Candidate, Place, PreferenceSpec
from services.candidate_search import search_candidates, resolve_anchor
from services.preferences import parse_preferences
from services.ranking import rank_candidates
from services.rerank import apply_rerank
from services.report import build_report
from services.details import fetch_details
from services.reasoner import build_reason
from services.bbox_builder import expand_bbox_from_center


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


def _clamp_rating(value: float) -> float:
    return max(0.5, min(5.0, value))


def _resolve_rating(candidate: Candidate) -> tuple[float, str]:
    if candidate.derived_rating is not None:
        return (round(_clamp_rating(candidate.derived_rating), 1), candidate.rating_source or "external")
    if candidate.place.rating is not None:
        return (round(_clamp_rating(candidate.place.rating), 1), "geoapify")
    fallback = _clamp_rating(candidate.score * 5.0)
    return (round(fallback, 1), "model_score")


class RecommendRequest(BaseModel):
    query: str = Field(..., description="Natural-language dining request")
    session_id: Optional[str] = Field(None, description="Session ID for conversation history")
    limit: int = Field(8, description="Number of results to enrich and return details for")
    user_lat: Optional[float] = Field(None, description="Optional user latitude for precise anchor")
    user_lon: Optional[float] = Field(None, description="Optional user longitude for precise anchor")


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
    debug_scores: Dict[str, float] = {}
    derived_rating: float
    rating_source: str
    match_mode: str


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
        if req.user_lat is not None and req.user_lon is not None:
            spec.anchor_lat = req.user_lat
            spec.anchor_lon = req.user_lon
        if not spec.city and (spec.anchor_lat is None or spec.anchor_lon is None):
            raise ValueError("Unable to parse a city or coordinate from the request. Please include a US city/area or enable location.")

        places, bbox = search_candidates(cfg, spec, min_results=req.limit)
        center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
        ranked = rank_candidates(spec, places, bbox_center=center, max_results=req.limit)
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
            ratings = []
            extracted = ctx.extracted or {}
            if isinstance(extracted.get("ratings"), list):
                ratings = [r for r in extracted["ratings"] if isinstance(r, (int, float))]
            if ratings:
                c.derived_rating = sum(ratings) / len(ratings)
                c.rating_source = "external"

        # Run in parallel
        await asyncio.gather(*(process_candidate(c) for c in ranked[:top_k]))

        for c in ranked:
            rating_value, rating_source = _resolve_rating(c)
            c.derived_rating = rating_value
            c.rating_source = rating_source

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
            debug_scores=c.debug_scores,
            derived_rating=c.derived_rating or 0.0,
            rating_source=c.rating_source or "model_score",
            match_mode=c.match_mode,
        )
        for c in ranked
    ]

    return RecommendResponse(
        recommendations_markdown=md,
        candidates=cands,
        preferences=spec.__dict__,
        bbox=bbox,
    )


@app.post("/recommend-stream")
async def recommend_stream(req: RecommendRequest):
    """
    SSE streaming endpoint for progressive restaurant recommendations.
    Returns candidates one by one as Server-Sent Events.
    """
    import json
    import asyncio
    
    try:
        cfg = Configuration.from_env()
        cfg.require_geoapify()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    
    
    async def event_generator():
        try:
            # Session handling
            from services.session import session_manager
            history = session_manager.get_history(req.session_id) if req.session_id else None

            # Parse preferences
            spec = await asyncio.to_thread(parse_preferences, cfg, req.query, history=history)
            if req.user_lat and req.user_lon:
                spec.anchor_lat = req.user_lat
                spec.anchor_lon = req.user_lon
            if not spec.city and (spec.anchor_lat is None or spec.anchor_lon is None):
                raise ValueError("Unable to parse a city or coordinate from the request.")

            # 1. Resolve Anchor (Geocoding) - Fast (T=0.2s)
            # Run in thread to avoid blocking loop
            anchor = await asyncio.to_thread(resolve_anchor, cfg, spec)
            center_lon, center_lat, _, _ = anchor
            
            # Calculate initial bbox for metadata (default 3km radius)
            initial_bbox = expand_bbox_from_center(center_lon, center_lat, 3.0)
            
            # IMMEDIATELY send metadata event
            metadata = {
                "type": "metadata",
                "preferences": spec.__dict__,
                "bbox": list(initial_bbox),
            }
            yield f"data: {json.dumps(metadata, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01) # Flush

            # 2. Search Candidates (POI Search) - Slower (T=2-9s)
            # Pass resolved anchor to skip re-geocoding
            places_initial, final_bbox = await asyncio.to_thread(
                search_candidates, cfg, spec, min_results=8, anchor=anchor
            )
            
            # Update bbox if it expanded
            if final_bbox != initial_bbox:
                metadata_update = {
                    "type": "metadata",
                    "preferences": spec.__dict__,
                    "bbox": list(final_bbox),
                }
                yield f"data: {json.dumps(metadata_update, ensure_ascii=False)}\n\n"

            center = ((final_bbox[0] + final_bbox[2]) / 2.0, (final_bbox[1] + final_bbox[3]) / 2.0)
            
            # Batch 1: Quick initial 8 candidates
            ranked_batch1 = rank_candidates(spec, places_initial, bbox_center=center, max_results=8)
            ranked_batch1 = apply_rerank(cfg, spec, ranked_batch1)
            
            # Helper to create payload from candidate object
            def _create_candidate_payload(c) -> CandidatePayload:
                # Ensure rating is resolved (fallback if None)
                if c.derived_rating is None:
                    d_rating, d_source = _resolve_rating(c)
                else:
                    d_rating, d_source = c.derived_rating, c.rating_source

                place_payload = PlacePayload(
                    name=c.place.name,
                    address=c.place.address,
                    lon=c.place.lon,
                    lat=c.place.lat,
                    website=c.place.website,
                    opening_hours=c.place.opening_hours,
                    datasource_url=c.place.datasource_url,
                    tags=c.place.tags,
                    rating=c.place.rating,
                )
                return CandidatePayload(
                    place=place_payload,
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
                    debug_scores=c.debug_scores,
                    derived_rating=d_rating,
                    rating_source=d_source or "unknown",
                    match_mode=c.match_mode,
                )

            # STAGE 1: Send PARTIAL results immediately (T=0.5s)
            # This gives immediate visual feedback while details are fetching
            for idx, c in enumerate(ranked_batch1[:8]):
                cand_payload = _create_candidate_payload(c)
                event_data = {
                    "type": "candidate",
                    "status": "partial",
                    "index": idx,
                    "total": req.limit,
                    "tier": c.match_tier,
                    "candidate": cand_payload.dict(),
                    "is_initial_batch": True,
                }
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)  # Tiny yield to ensure flush

            # STAGE 2: Enrich and send FULL results (T=6s)
            from services.details import fetch_details_async
            
            # Helper function to fully enrich a single candidate
            async def enrich_candidate(idx: int, c):
                """Fetch details and build reason for one candidate"""
                start_time = time.time()
                try:
                    # Fetch details (DuckDuckGo search)
                    ctx = await fetch_details_async(c.place, lang=spec.lang or cfg.lang_default)
                    
                    # Build reason (LLM call)
                    reason = await asyncio.to_thread(build_reason, cfg, spec, c.place, ctx)
                    
                    duration = time.time() - start_time
                    logger.debug(f"Candidate {idx} enriched in {duration:.2f}s")
                    
                    # Apply enrichment
                    c.highlights = _to_str_list(reason.get("highlights"))
                    c.signature_dishes = _to_str_list(reason.get("signature_dishes"))
                    c.why_matched = _to_str_list(reason.get("why_matched"))
                    c.risks = _to_str_list(reason.get("risks"))
                    c.detail_sources = list(ctx.sources or [])
                    c.source_hits = ctx.hits
                    c.source_trust_score = ctx.trust_score
                    
                    # Extract ratings
                    ratings = []
                    extracted = ctx.extracted or {}
                    if isinstance(extracted.get("ratings"), list):
                        ratings = [r for r in extracted["ratings"] if isinstance(r, (int, float))]
                    if ratings:
                        c.derived_rating = sum(ratings) / len(ratings)
                        c.rating_source = "external"
                    
                    # Resolve final rating
                    rating_value, rating_source = _resolve_rating(c)
                    c.derived_rating = rating_value
                    c.rating_source = rating_source
                    
                    return (idx, c, None)  # Success
                except Exception as exc:
                    logger.error(f"Failed to enrich candidate {idx}: {exc}")
                    return (idx, c, str(exc))  # Return error
            
            # Create enrichment tasks for all 8 candidates
            enrichment_tasks = {}
            for idx, c in enumerate(ranked_batch1[:8]):
                task = asyncio.create_task(enrich_candidate(idx, c))
                enrichment_tasks[task] = (idx, c)
            
            # Process and stream results AS SOON AS EACH COMPLETES
            for completed_task in asyncio.as_completed(enrichment_tasks.keys()):
                idx, c, error = await completed_task
                
                if error:
                    logger.warning(f"Skipping candidate {idx} due to error: {error}")
                    continue
                
                # Convert to payload (now fully enriched)
                cand_payload = _create_candidate_payload(c)
                
                # Create SSE event and send IMMEDIATELY
                event_data = {
                    "type": "candidate",
                    "status": "full",  # Update existing partial
                    "index": idx,
                    "total": req.limit,
                    "tier": c.match_tier,
                    "candidate": cand_payload.dict(),
                    "is_initial_batch": True,
                }
                
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                
                # Small delay for visual effect
                await asyncio.sleep(0.02)
            
            
            # Batch 2: Continue streaming remaining candidates with TRUE STREAMING
            if req.limit > 8:
                # Search for more candidates
                places_all, _ = search_candidates(cfg, spec, min_results=req.limit)
                ranked_all = rank_candidates(spec, places_all, bbox_center=center, max_results=req.limit)
                ranked_all = apply_rerank(cfg, spec, ranked_all)
                
                # Get candidates from index 8 onwards (skip first batch)
                remaining_candidates = ranked_all[8:req.limit]
                
                # STAGE 1 (Batch 2): Send PARTIAL results
                for idx, c in enumerate(remaining_candidates, start=8):
                    cand_payload = _create_candidate_payload(c)
                    event_data = {
                        "type": "candidate",
                        "status": "partial",
                        "index": idx,
                        "total": req.limit,
                        "tier": c.match_tier,
                        "candidate": cand_payload.dict(),
                        "is_initial_batch": False,
                    }
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.01)

                # STAGE 2 (Batch 2): Enrich and send FULL results
                enrichment_tasks_batch2 = {}
                for idx, c in enumerate(remaining_candidates, start=8):
                    task = asyncio.create_task(enrich_candidate(idx, c))
                    enrichment_tasks_batch2[task] = (idx, c)
                
                # Process and stream AS SOON AS EACH COMPLETES
                for completed_task in asyncio.as_completed(enrichment_tasks_batch2.keys()):
                    idx, c, error = await completed_task
                    
                    if error:
                        logger.warning(f"Skipping candidate {idx} due to error: {error}")
                        continue
                    
                    cand_payload = _create_candidate_payload(c)
                    
                    event_data = {
                        "type": "candidate",
                        "status": "full",
                        "index": idx,
                        "total": req.limit,
                        "tier": c.match_tier,
                        "candidate": cand_payload.dict(),
                        "is_initial_batch": False,
                    }
                    
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                    
                    # Small delay for visual effect
                    await asyncio.sleep(0.02)
            
            # Signal completion
            yield 'data: {"type":"complete"}\n\n'
            
        except Exception as exc:
            logger.exception("streaming failed: {}", exc)
            error_data = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)
