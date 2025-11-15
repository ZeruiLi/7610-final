from __future__ import annotations

import os
from typing import Any, Optional

from pydantic import BaseModel, Field

from utils import mask_secret


class Configuration(BaseModel):
    # Geoapify
    geoapify_api_key: Optional[str] = Field(default=None)
    geoapify_base_url: str = Field(default="https://api.geoapify.com")
    geoapify_timeout: int = Field(default=15)
    geoapify_max_results: int = Field(default=20)

    # Defaults
    default_distance_km: float = Field(default=3.0)
    bbox_padding_km: float = Field(default=0.6)
    lang_default: str = Field(default="en")

    # LLM (optional, same semantics as deepresearch)
    local_llm: Optional[str] = Field(default=None)
    llm_provider: Optional[str] = Field(default=None)
    llm_api_key: Optional[str] = Field(default=None)
    llm_base_url: Optional[str] = Field(default=None)
    llm_model_id: Optional[str] = Field(default=None)
    # native ollama base (without /v1)
    ollama_base_url: str = Field(default="http://localhost:11434")

    # Rerank
    rerank_enabled: bool = Field(default=False)
    rerank_weight: float = Field(default=0.4)
    rerank_top_n: int = Field(default=10)
    rerank_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")

    @classmethod
    def from_env(cls, overrides: Optional[dict[str, Any]] = None) -> "Configuration":
        raw: dict[str, Any] = {}

        env_map = {
            "geoapify_api_key": os.getenv("GEOAPIFY_API_KEY"),
            "geoapify_base_url": os.getenv("GEOAPIFY_BASE_URL"),
            "geoapify_timeout": os.getenv("GEOAPIFY_TIMEOUT"),
            "geoapify_max_results": os.getenv("GEOAPIFY_MAX_RESULTS"),
            "default_distance_km": os.getenv("DEFAULT_DISTANCE_KM"),
            "bbox_padding_km": os.getenv("BBOX_PADDING_KM"),
            "lang_default": os.getenv("LANG_DEFAULT"),
            # LLM
            "local_llm": os.getenv("LOCAL_LLM"),
            "llm_provider": os.getenv("LLM_PROVIDER"),
            "llm_api_key": os.getenv("LLM_API_KEY"),
            "llm_base_url": os.getenv("LLM_BASE_URL"),
            "llm_model_id": os.getenv("LLM_MODEL_ID"),
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL"),
            "rerank_enabled": os.getenv("RERANK_ENABLED"),
            "rerank_weight": os.getenv("RERANK_WEIGHT"),
            "rerank_top_n": os.getenv("RERANK_TOP_N"),
            "rerank_model": os.getenv("RERANK_MODEL"),
        }

        bool_fields = {"rerank_enabled"}

        for k, v in env_map.items():
            if v is None:
                continue
            if k in bool_fields:
                raw[k] = str(v).lower() in {"1", "true", "yes", "on"}
            else:
                raw[k] = v

        if overrides:
            raw.update({k: v for k, v in overrides.items() if v is not None})

        return cls(**raw)

    def require_geoapify(self) -> None:
        if not self.geoapify_api_key:
            raise ValueError("GEOAPIFY_API_KEY is required")

    def log_summary(self) -> str:
        return (
            "geoapify=%s base=%s timeout=%s max_results=%s lang_default=%s api_key=%s"
            % (
                bool(self.geoapify_api_key),
                self.geoapify_base_url,
                self.geoapify_timeout,
                self.geoapify_max_results,
                self.lang_default,
                mask_secret(self.geoapify_api_key),
            )
        )

    def sanitized_ollama_url(self) -> str:
        base = (self.ollama_base_url or "http://localhost:11434").rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return base
