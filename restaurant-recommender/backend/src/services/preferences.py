from __future__ import annotations

import json
from typing import Any, Optional
import re

from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent

from config import Configuration
from models import PreferenceSpec
from utils import strip_thinking_tokens

HOTPOT_KEYWORDS = [
    "hot pot",
    "hotpot",
    "shabu",
    "shabu-shabu",
    "haidilao",
    "liuyishou",
    "boiling point",
    "little sheep",
    "mala tang",
]

NO_SPICY_KEYWORDS = [
    "no spicy",
    "not spicy",
    "mild",
    "low spice",
    "non-spicy",
    "无辣",
    "不要辣",
]

DAY_OF_WEEK = {
    "monday": "Mon",
    "tuesday": "Tue",
    "wednesday": "Wed",
    "thursday": "Thu",
    "friday": "Fri",
    "saturday": "Sat",
    "sunday": "Sun",
}


SYSTEM_PROMPT = (
    "You are a preference parser for a restaurant recommender.\n"
    "Return a JSON object only, using the keys: city, area, datetime, people, budget_per_capita, cuisines, taboos, ambiance, "
    "need_private_room, rating_min, distance_km, lang, must_include_cuisines, must_exclude_cuisines, dining_time, min_duration_min, "
    "strict_open_check. Values should be simple (strings, numbers, booleans, arrays).\n"
    "Example: {\"city\":\"Seattle\",\"area\":\"Capitol Hill\",\"people\":2,\"budget_per_capita\":45,\"cuisines\":[\"Vegetarian\"],"
    "\"ambiance\":[\"Quiet\"],\"need_private_room\":false,\"rating_min\":4.0,\"distance_km\":3,\"lang\":\"en\","
    "\"must_include_cuisines\":[\"Hotpot\"],\"must_exclude_cuisines\":[\"Spicy\"],\"dining_time\":\"Tue 20:00\",\"min_duration_min\":75,\"strict_open_check\":true}"
)


class PreferencesParser:
    def __init__(self, cfg: Configuration) -> None:
        self.cfg = cfg
        self.llm = self._init_llm(cfg)
        self.agent = ToolAwareSimpleAgent(
            name="PreferenceParser",
            llm=self.llm,
            system_prompt=SYSTEM_PROMPT,
            enable_tool_calling=False,
        )

    def _init_llm(self, cfg: Configuration) -> HelloAgentsLLM:
        kwargs: dict[str, Any] = {"temperature": 0.0}
        if cfg.llm_model_id or cfg.local_llm:
            kwargs["model"] = (cfg.llm_model_id or cfg.local_llm)
        if cfg.llm_provider:
            kwargs["provider"] = cfg.llm_provider
        # prefer explicit llm_base_url; for ollama, fallback to sanitized /v1
        if cfg.llm_base_url:
            kwargs["base_url"] = cfg.llm_base_url
        elif (cfg.llm_provider or "").lower() == "ollama":
            kwargs["base_url"] = cfg.sanitized_ollama_url()
        if cfg.llm_api_key:
            kwargs["api_key"] = cfg.llm_api_key
        return HelloAgentsLLM(**kwargs)

    def parse(self, text: str, history: list[dict] | None = None) -> PreferenceSpec:
        prompt = text
        if history:
            hist_str = "\n".join([f"{t['role']}: {t['content']}" for t in history])
            prompt = f"HISTORY:\n{hist_str}\n\nCURRENT REQUEST: {text}"
        
        raw = self.agent.run(prompt)
        self.agent.clear_history()
        cleaned = strip_thinking_tokens(raw).strip()
        # locate JSON braces if extra text remains
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        data: dict[str, Any] = {}
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                data = {}

        return _to_spec(self.cfg, data)


def _to_spec(cfg: Configuration, data: dict[str, Any]) -> PreferenceSpec:
    # defaults and coercions
    city = str(data.get("city") or "").strip()
    if not city:
        # fall back to area if provided
        city = str(data.get("area") or "").strip()
    if not city:
        # final fallback to avoid crash; caller should validate
        city = ""

    distance = data.get("distance_km")
    try:
        distance_km = float(distance) if distance is not None else cfg.default_distance_km
    except (TypeError, ValueError):
        distance_km = cfg.default_distance_km

    people_val = data.get("people")
    people = None
    try:
        if people_val is not None:
            people = int(float(str(people_val).strip()))
    except (TypeError, ValueError):
        people = None

    must_include = [str(x).strip() for x in (data.get("must_include_cuisines") or []) if str(x).strip()]
    must_exclude = [str(x).strip() for x in (data.get("must_exclude_cuisines") or []) if str(x).strip()]

    dining_time = str(data.get("dining_time") or "").strip() or None

    duration_val = data.get("min_duration_min")
    try:
        min_duration = int(duration_val) if duration_val is not None else 60
    except (TypeError, ValueError):
        min_duration = 60

    strict_open_val = data.get("strict_open_check")
    if isinstance(strict_open_val, str):
        strict_open = strict_open_val.strip().lower() in {"true", "1", "yes", "on"}
    elif isinstance(strict_open_val, (int, float)):
        strict_open = bool(strict_open_val)
    elif isinstance(strict_open_val, bool):
        strict_open = strict_open_val
    else:
        strict_open = True

    spec = PreferenceSpec(
        city=city,
        area=(str(data.get("area")).strip() if data.get("area") else None),
        datetime=(str(data.get("datetime")).strip() if data.get("datetime") else None),
        people=people,
        budget_per_capita=(float(data.get("budget_per_capita")) if isinstance(data.get("budget_per_capita"), (int, float)) else None),
        cuisines=[str(x).strip() for x in (data.get("cuisines") or []) if str(x).strip()],
        taboos=[str(x).strip() for x in (data.get("taboos") or []) if str(x).strip()],
        ambiance=[str(x).strip() for x in (data.get("ambiance") or []) if str(x).strip()],
        need_private_room=bool(data.get("need_private_room")) if data.get("need_private_room") is not None else None,
        rating_min=(float(data.get("rating_min")) if isinstance(data.get("rating_min"), (int, float)) else None),
        distance_km=distance_km,
        lang=(str(data.get("lang")).strip() if data.get("lang") else cfg.lang_default),
        must_include_cuisines=must_include,
        must_exclude_cuisines=must_exclude,
        dining_time=dining_time,
        min_duration_min=min_duration,
        strict_open_check=strict_open,
    )
    return spec


def _likely_english(text: str) -> bool:
    # crude heuristic: contains 'Seattle' or mostly ASCII letters
    if "seattle" in text.lower():
        return True
    ascii_letters = sum(ch.isascii() and ch.isalpha() for ch in text)
    return ascii_letters / max(1, len(text)) > 0.6


def _extract_dining_time(text: str) -> tuple[Optional[str], int, bool]:
    import re

    lower = text.lower()
    day_token: Optional[str] = None
    for full, abbr in DAY_OF_WEEK.items():
        if full in lower:
            day_token = abbr
            break

    time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lower)
    if not time_match:
        time_match = re.search(r"at\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lower)
    if not time_match:
        time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(?:o'clock)\s*(pm|am)?", lower)

    dining_time = None
    start_minutes: Optional[int] = None
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        meridiem = time_match.group(3)
        if meridiem:
            if meridiem == "pm" and hour != 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
        hour %= 24
        start_minutes = hour * 60 + minute
        dining_time = f"{hour:02d}:{minute:02d}"

        context_window = lower[max(0, time_match.start() - 25) : time_match.start()]
        if re.search(r"after|ends?|finishes|finish|gets out|wraps up", context_window):
            start_minutes += 15
            hour = (start_minutes // 60) % 24
            minute = start_minutes % 60
            dining_time = f"{hour:02d}:{minute:02d}"

    # duration detection (e.g., "for 90 minutes")
    duration_match = re.search(r"for\s*(\d{1,3})\s*(?:minutes|min)", lower)
    duration = 60
    if duration_match:
        try:
            duration = max(30, int(duration_match.group(1)))
        except ValueError:
            duration = 60

    # heuristics: after/ends at implies longer stay
    if start_minutes is not None and re.search(r"after\s+\d|ends?\s+at", lower):
        duration = max(duration, 75)

    closing_minutes: Optional[int] = None
    closing_match = re.search(r"open\s+(?:until|till|through)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)", lower)
    if closing_match:
        hour = int(closing_match.group(1))
        minute = int(closing_match.group(2) or 0)
        meridiem = closing_match.group(3)
        if meridiem:
            if meridiem == "pm" and hour != 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
        hour %= 24
        closing_minutes = hour * 60 + minute
    elif "open late" in lower:
        closing_minutes = 22 * 60  # default 10 PM requirement

    if closing_minutes is not None:
        if start_minutes is None:
            # assume dining roughly 2 hours before closing, but no earlier than 20:15
            start_minutes = max(20 * 60 + 15, closing_minutes - 120)
            dining_hour = (start_minutes // 60) % 24
            dining_minute = start_minutes % 60
            dining_time = f"{dining_hour:02d}:{dining_minute:02d}"
        span = closing_minutes - start_minutes
        if span <= 0:
            span += 24 * 60
        duration = max(duration, min(180, span))

    strict = True
    if re.search(r"flexible|if possible|preferably", lower):
        strict = False

    if dining_time and day_token:
        return (f"{day_token} {dining_time}", duration, strict)
    if dining_time:
        return (dining_time, duration, strict)
    return (None, duration, strict)


def parse_with_rules(cfg: Configuration, text: str) -> PreferenceSpec:
    import re

    t = text.strip()
    lower = t.lower()
    lang = "en" if _likely_english(t) else cfg.lang_default

    city = None
    area = None
    city_map = {
        "seattle": "Seattle",
        "san francisco": "San Francisco",
        "sf": "San Francisco",
        "new york": "New York",
        "nyc": "New York",
        "los angeles": "Los Angeles",
        "la": "Los Angeles",
        "austin": "Austin",
    }
    for token, label in city_map.items():
        if token in lower:
            city = label
            break

    area_map = {
        "capitol hill": "Capitol Hill",
        "u district": "U District",
        "university district": "U District",
        "south lake union": "South Lake Union",
        "soma": "SoMa",
        "mission district": "Mission District",
        "flushing": "Flushing",
        "koreatown": "Koreatown",
        "south congress": "South Congress",
        "the domain": "Domain",
    }
    for token, label in area_map.items():
        if token in lower:
            area = label
            break

    distance_km = cfg.default_distance_km
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:km|kilometers|kilometres)", lower)
    if m:
        try:
            distance_km = float(m.group(1))
        except ValueError:
            pass
    else:
        m2 = re.search(r"(\d+(?:\.\d+)?)\s*(?:mile|miles|mi)", lower)
        if m2:
            try:
                distance_km = float(m2.group(1)) * 1.60934
            except ValueError:
                pass

    people = None
    m = re.search(r"(\d+)\s*(?:people|guests|classmates|friends|person|ppl)", lower)
    if m:
        try:
            people = int(m.group(1))
        except ValueError:
            pass

    budget = None
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)", lower)
    if not m:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:usd|dollars|bucks)", lower)
    if m:
        try:
            budget = float(m.group(1))
        except ValueError:
            pass

    cuisines: list[str] = []
    for kw in ["sushi", "ramen", "korean bbq", "bbq", "pizza", "italian", "thai", "mexican", "vegan", "steak"]:
        if kw in lower:
            cuisines.append(kw.title())

    must_include: list[str] = []
    if any(keyword in lower for keyword in HOTPOT_KEYWORDS):
        must_include.append("Hotpot")
        cuisines.append("Hotpot")

    must_exclude: list[str] = []
    if any(keyword in lower for keyword in NO_SPICY_KEYWORDS):
        must_exclude.append("Spicy")

    ambiance: list[str] = []
    if re.search(r"quiet|calm|low-noise|study-friendly|安静", lower):
        ambiance.append("Quiet")
    if "romantic" in lower:
        ambiance.append("Romantic")
    if "casual" in lower:
        ambiance.append("Casual")

    dining_time, min_duration, strict_open = _extract_dining_time(t)

    data = {
        "city": city or "",
        "area": area,
        "distance_km": distance_km,
        "people": people,
        "budget_per_capita": budget,
        "cuisines": cuisines,
        "ambiance": ambiance,
        "lang": lang,
        "must_include_cuisines": must_include,
        "must_exclude_cuisines": must_exclude,
        "dining_time": dining_time,
        "min_duration_min": min_duration,
        "strict_open_check": strict_open,
    }
    return _to_spec(cfg, data)


def parse_preferences(cfg: Configuration, text: str, history: list[dict] | None = None) -> PreferenceSpec:
    """Parse preferences using LLM when configured, otherwise fall back to rules."""
    llm_available = bool(cfg.llm_provider or cfg.llm_base_url or cfg.local_llm)
    if not llm_available:
        combined_text = text
        if history:
            combined_text = " ".join([str(t.get("content", "")) for t in history]) + " " + text
        spec = parse_with_rules(cfg, combined_text)
        return _post_process_preferences(text, spec)

    # fallback logic
    combined_text = text
    if history:
        # Simple concatenation to allow rule-based parser to see previous context (e.g. city)
        combined_text = " ".join([str(t.get("content", "")) for t in history]) + " " + text

    try:
        parser = PreferencesParser(cfg)
        spec = parser.parse(text, history)
        if not spec.city:
            # attempt rules fallback if city missing, using combined text
            spec = parse_with_rules(cfg, combined_text)
        return _post_process_preferences(text, spec)
    except Exception:
        # fallback on any LLM failure
        spec = parse_with_rules(cfg, combined_text)
    return _post_process_preferences(text, spec)


def _post_process_preferences(text: str, spec: PreferenceSpec) -> PreferenceSpec:
    """Apply heuristic adjustments that depend on the original text."""
    if _has_strong_pizza_intent(text) and not _has_pizza_negation(text):
        if "Pizza" not in spec.must_include_cuisines:
            spec.must_include_cuisines.append("Pizza")
        if "Pizza" not in spec.cuisines:
            spec.cuisines.append("Pizza")

    # Add spicy/hot keyword detection
    text_lower = text.lower()
    spicy_keywords = ["spicy", "hot", "mala", "sichuan", "hunan", "chongqing"]
    if any(kw in text_lower for kw in spicy_keywords):
        # Only add to cuisines for ranking boost, NOT to must_include (which forces filtering)
        if "spicy" not in [c.lower() for c in spec.cuisines]:
            spec.cuisines.append("Spicy")

    anchor_poi, anchor_zip = _extract_location_signals(text)
    if anchor_poi and not spec.anchor_poi:
        spec.anchor_poi = anchor_poi.strip()
    if anchor_zip and not spec.anchor_zip:
        spec.anchor_zip = anchor_zip.strip()

    derived_time, derived_duration, derived_strict = _extract_dining_time(text)
    if derived_time and not (spec.dining_time and str(spec.dining_time).strip()):
        spec.dining_time = derived_time
    if derived_duration and derived_duration > spec.min_duration_min:
        spec.min_duration_min = derived_duration
    spec.strict_open_check = spec.strict_open_check and derived_strict
    return spec


PIZZA_INTENT_PATTERNS = [
    r"\b(?:love|would love|want|crave|craving|need|prefer|treat(?:ing)?).{0,40}\bpizza\b",
    r"\bpizza\b.{0,20}\b(?:place|spot|restaurant)\b",
    r"\b(?:grab|enjoy).{0,20}\bpizza\b",
]

# Chinese expressions for strong pizza intent
PIZZA_INTENT_CHINESE = [
    "想吃披萨",
    "很想吃披萨",
    "特别想吃披萨",
    "请吃披萨",
    "吃披萨",
]

PIZZA_NEGATION_PATTERNS = [
    r"\b(?:no|not|avoid|without)\b.{0,20}\bpizza\b",
]

PIZZA_NEGATION_CHINESE = [
    "不要披萨",
    "不吃披萨",
]


def _has_strong_pizza_intent(text: str) -> bool:
    lowered = text.lower()
    if "pizza" not in lowered and not any(phrase in text for phrase in PIZZA_INTENT_CHINESE):
        return False
    for pattern in PIZZA_INTENT_PATTERNS:
        if re.search(pattern, lowered):
            return True
    return any(phrase in text for phrase in PIZZA_INTENT_CHINESE)


def _has_pizza_negation(text: str) -> bool:
    lowered = text.lower()
    for pattern in PIZZA_NEGATION_PATTERNS:
        if re.search(pattern, lowered):
            return True
    return any(phrase in text for phrase in PIZZA_NEGATION_CHINESE)


POI_KEYWORDS = [
    "university",
    "college",
    "campus",
    "hospital",
    "center",
    "station",
    "museum",
]

POI_KEYWORDS_CHINESE = [
    "大学",
    "学院",
    "医院",
    "中心",
    "地铁站",
    "火车站",
]


def _extract_location_signals(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract POI name and ZIP code (US) from free text."""
    poi: Optional[str] = None
    zip_code: Optional[str] = None

    # ZIP code (US 5-digit or ZIP+4)
    zip_match = re.search(r"\\b(\\d{5})(?:-\\d{4})?\\b", text)
    if zip_match:
        zip_code = zip_match.group(0)

    lowered = text.lower()
    # English POI detection: look for capitalized phrase ending with keyword
    if not poi:
        for keyword in POI_KEYWORDS:
            idx = lowered.find(keyword)
            if idx != -1:
                start = max(0, idx - 60)
                fragment = text[start : idx + len(keyword)]
                pattern = rf"([A-Z][\w&.'-]+(?:\s+[A-Z][\w&.'-]+){{0,3}}\s+(?i:{keyword}))"
                match = re.search(pattern, fragment)
                if match:
                    candidate = match.group(1).strip(" ,")
                    if len(candidate) >= len(keyword) + 2:
                        poi = candidate
                        break

    if not poi:
        # Chinese POI detection
        for keyword in POI_KEYWORDS_CHINESE:
            idx = text.find(keyword)
            if idx != -1:
                start = max(0, idx - 10)
                fragment = text[start : idx + len(keyword)]
                match = re.search(r"([\\u4e00-\\u9fa5A-Za-z0-9]{2,}" + keyword + r")", fragment)
                if match:
                    poi = match.group(1)
                    break

    return poi, zip_code
