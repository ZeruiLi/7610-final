from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent

from config import Configuration
from models import Place, PreferenceSpec
from services.details import DetailContext
from utils import strip_thinking_tokens


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


def _init_llm(cfg: Configuration) -> HelloAgentsLLM:
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
    return HelloAgentsLLM(**kw)


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
        if dishes:
            highlights.append(f"Known for: {', '.join(dishes[:4])}")
        if detail.extracted.get("ratings"):
            highlights.append(f"Ratings reported: {', '.join(detail.extracted['ratings'][:2])}")
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

    agent = ToolAwareSimpleAgent(
        name="Reasoner",
        llm=_init_llm(cfg),
        system_prompt=(
            "You are a restaurant guide. Using the diner preferences, venue metadata and the"
            " trusted sources below, produce a JSON object with: \n"
            "- highlights: 3-5 bullet points grounded in the sources\n"
            "- signature_dishes: 2-4 popular dishes or categories\n"
            "- why_matched: reasons this venue fits the stated preferences (cuisine/ambience/budget/etc.)\n"
            "- risks: uncertainties or caveats the diner should verify\n"
            "Only output JSON. If information is missing, be explicit instead of hallucinating."
        ),
        enable_tool_calling=False,
    )
    prompt = (
        "DINER PREFERENCES:" + json.dumps(spec.__dict__, ensure_ascii=False) + "\n"
        f"RESTAURANT: name={place.name}, address={place.address}, lat={place.lat}, lon={place.lon}\n"
        f"TRUST_SCORE: {detail.trust_score}, SOURCE_COUNT: {detail.hits}\n"
        f"SOURCES SNIPPET:\n{detail_text[:3000]}\n"
        "Return JSON object only."
    )
    raw = agent.run(prompt)
    agent.clear_history()
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
