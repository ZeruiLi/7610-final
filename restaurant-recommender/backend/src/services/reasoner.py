from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Union

from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
from loguru import logger

from config import Configuration
from models import Place, PreferenceSpec
from services.details import DetailContext
from utils import strip_thinking_tokens

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


DISH_KWS = [
    "ramen", "sushi", "udon", "tempura", "donburi", "yakitori",
    "pho", "banh mi", "spring roll",
    "bbq", "brisket", "steak", "burger",
    "pizza", "pasta", "risotto",
    "taco", "burrito",
    "hotpot", "dumpling", "noodle", "noodles",
]


def _extract_keywords(text: str, kws: List[str]) -> List[str]:
    out: List[str] = []
    low = text.lower()
    for k in kws:
        if re.search(r"\b" + re.escape(k) + r"\b", low):
            out.append(k)
    return list(dict.fromkeys(out))[:6]


def _init_llm(cfg: Configuration) -> tuple[Union[genai.Client, HelloAgentsLLM], str]:
    """Initialize LLM with Gemini primary and Ollama fallback."""
    provider = (cfg.llm_provider or "").lower()
    
    # Try Gemini first if configured
    if provider == "google" and GEMINI_AVAILABLE and cfg.llm_api_key:
        try:
            import os
            os.environ["GEMINI_API_KEY"] = cfg.llm_api_key
            client = genai.Client()
            model_id = cfg.llm_model_id or "gemini-2.0-flash-exp"
            logger.debug(f"Reasoner using Gemini model: {model_id}")
            return client, "gemini"
        except Exception as e:
            logger.warning(f"Gemini initialization failed in reasoner: {e}, falling back to Ollama")
    
    # Fallback to Ollama or other providers
    kw: Dict[str, Any] = {"temperature": 0.1}
    if cfg.llm_model_id or cfg.local_llm:
        kw["model"] = cfg.llm_model_id or cfg.local_llm
    if cfg.llm_provider:
        kw["provider"] = cfg.llm_provider
    if cfg.llm_base_url:
        kw["base_url"] = cfg.llm_base_url
    elif (cfg.llm_provider or "").lower() == "ollama":
        kw["base_url"] = cfg.sanitized_ollama_url()
    if cfg.llm_api_key:
        kw["api_key"] = cfg.llm_api_key
    return HelloAgentsLLM(**kw), "ollama"


def build_reason(
    cfg: Configuration,
    spec: PreferenceSpec,
    place: Place,
    detail: DetailContext,
) -> Dict[str, Any]:
    """Return a structured reason payload. Falls back to rules if no LLM."""
    use_llm = bool(cfg.llm_provider or cfg.llm_base_url or cfg.local_llm)
    detail_text = detail.raw_text or ""

    if not use_llm:
        dishes = _extract_keywords(detail_text, DISH_KWS)
        highlights: list[str] = []
        
        # Fallback using tags if no dishes found
        if not dishes and place.tags:
            # Filter out generic tags
            meaningful_tags = []
            for t in place.tags:
                clean = t.replace("catering.", "").replace("_", " ")
                if clean not in ("restaurant", "food", "point of interest"):
                    meaningful_tags.append(clean.title())
            
            if meaningful_tags:
                highlights.append(f"Specializes in: {', '.join(meaningful_tags[:3])}")
        
        if dishes:
            highlights.append(f"Known for: {', '.join(dishes[:4])}")
            
        if detail.extracted.get("ratings"):
            highlights.append(f"Ratings reported: {', '.join(detail.extracted['ratings'][:2])}")
        elif place.rating:
            highlights.append(f"Overall rating: {place.rating}/5.0")
            
        if detail.hits:
            highlights.append(f"{detail.hits} reliable sources referenced")

        why: list[str] = []
        if spec.cuisines:
            why.append("Cuisine preference referenced; verify dishes with the sources")
        if spec.must_include_cuisines:
            why.append(f"Hard requirement satisfied: {', '.join(spec.must_include_cuisines)}")
        if spec.ambiance:
            why.append("Ambience preference not fully confirmed; consider contacting the venue")

        risks = []
        if not detail.hits:
            risks.append("Could not find trusted reviews; double-check availability")
        if detail.trust_score < 0.6:
            risks.append("Source reliability is limited; confirm via official site")
        if not risks:
            risks.append("Some information might be outdated; please verify with the source links")
        return {
            "highlights": highlights,
            "signature_dishes": dishes[:4],
            "why_matched": why,
            "risks": risks,
        }

    llm_client, llm_type = _init_llm(cfg)
    system_prompt = (
        "You are a restaurant guide. Using the diner preferences, venue metadata and the"
        " trusted sources below, produce a JSON object with: \n"
        "- highlights: 3-5 bullet points grounded in the sources. If sources are thin, use the provided TAGS and RATING to infer highlights.\n"
        "- signature_dishes: 2-4 popular dishes or categories\n"
        "- why_matched: reasons this venue fits the stated preferences (cuisine/ambience/budget/etc.)\n"
        "- risks: uncertainties or caveats the diner should verify\n"
        "Only output JSON. If information is missing, be explicit instead of hallucinating."
    )
    
    # Prepare fallback context if sources are empty
    fallback_context = ""
    if not detail.hits:
        fallback_context = f"NOTE: No external reviews found. Rely on TAGS: {place.tags} and RATING: {place.rating}."
        
    prompt = (
        "DINER PREFERENCES:" + json.dumps(spec.__dict__, ensure_ascii=False) + "\n"
        f"RESTAURANT: name={place.name}, address={place.address}, lat={place.lat}, lon={place.lon}\n"
        f"TAGS: {place.tags}, RATING: {place.rating}\n"
        f"TRUST_SCORE: {detail.trust_score}, SOURCE_COUNT: {detail.hits}\n"
        f"SOURCES SNIPPET:\n{detail_text[:3000]}\n"
        f"{fallback_context}\n"
        "Return JSON object only."
    )
    
    try:
        if llm_type == "gemini":
            # Use Gemini native client
            model_id = cfg.llm_model_id or "gemini-2.0-flash-exp"
            full_prompt = f"{system_prompt}\n\n{prompt}"
            response = llm_client.models.generate_content(
                model=model_id,
                contents=full_prompt
            )
            raw = response.text
        else:
            # Use HelloAgentsLLM
            agent = ToolAwareSimpleAgent(
                name="Reasoner",
                llm=llm_client,
                system_prompt=system_prompt,
                enable_tool_calling=False,
            )
            raw = agent.run(prompt)
            agent.clear_history()
    except Exception:
        return {
            "highlights": [],
            "signature_dishes": [],
            "why_matched": [],
            "risks": ["LLM reasoning failed; review sources manually if available."],
        }
    
    text = strip_thinking_tokens(raw)
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(text[s : e + 1])
        except Exception:
            pass
    # fallback minimal
    dishes = _extract_keywords(detail_text, DISH_KWS)
    return {
        "highlights": [],
        "signature_dishes": dishes[:4],
        "why_matched": [],
        "risks": ["Structured response unavailable; review the source links manually."],
    }
