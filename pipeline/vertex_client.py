"""Vertex AI client wrapper using google-genai SDK with strict config mapping and logging."""

import json
import time
from pathlib import Path
from typing import Any, Optional
from google import genai
from google.genai import types


def map_thinking_config(thinking_str: str) -> types.ThinkingConfig:
    """Maps VERSIONS.yaml thinking strings ('low', 'medium', 'high') to types.ThinkingConfig."""
    mapping = {
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
    }
    val = mapping.get(thinking_str.lower().strip())
    if not val:
        raise ValueError(f"Invalid thinking setting '{thinking_str}'. Must be one of: low, medium, high.")
    return types.ThinkingConfig(thinking_level=val)


def map_media_resolution(res_str: str) -> str:
    """Maps media resolution strings ('low', 'medium', 'high') to MEDIA_RESOLUTION constants."""
    mapping = {
        "low": "MEDIA_RESOLUTION_LOW",
        "medium": "MEDIA_RESOLUTION_MEDIUM",
        "high": "MEDIA_RESOLUTION_HIGH",
    }
    val = mapping.get(res_str.lower().strip())
    if not val:
        raise ValueError(f"Invalid media_resolution setting '{res_str}'. Must be one of: low, medium, high.")
    return val


def log_call(log_path: Path, record: dict[str, Any]) -> None:
    """Appends a single call metadata record to a JSONL log file (e.g. calls.jsonl)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


class VertexClient:
    def __init__(self, project: str = "nodepeel", location: str = "global", log_path: Optional[Path] = None) -> None:
        self.project = project
        self.location = location
        self.client = genai.Client(vertexai=True, project=project, location=location)
        self.log_path = log_path

    def generate(
        self,
        model: str,
        contents: list[Any],
        thinking_str: Optional[str] = None,
        media_resolution_str: Optional[str] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
        response_schema: Optional[Any] = None,
        response_mime_type: Optional[str] = None,
        pass_name: str = "",
        case_id: str = "",
        run_id: str = "",
    ) -> Any:
        config_kwargs: dict[str, Any] = {}
        resolved_thinking = None
        resolved_media_res = None

        if thinking_str:
            thinking_cfg = map_thinking_config(thinking_str)
            config_kwargs["thinking_config"] = thinking_cfg
            resolved_thinking = thinking_cfg.thinking_level

        if media_resolution_str:
            res_val = map_media_resolution(media_resolution_str)
            config_kwargs["media_resolution"] = res_val
            resolved_media_res = res_val

        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if seed is not None:
            config_kwargs["seed"] = seed
        if response_schema is not None:
            config_kwargs["response_schema"] = response_schema
        if response_mime_type is not None:
            config_kwargs["response_mime_type"] = response_mime_type

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        t0 = time.time()
        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        latency = time.time() - t0

        prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) if hasattr(response, "usage_metadata") else 0
        cand_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) if hasattr(response, "usage_metadata") else 0
        finish_reason = str(response.candidates[0].finish_reason) if response.candidates else "UNKNOWN"

        if self.log_path:
            record = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "case_id": case_id,
                "run_id": run_id,
                "pass_name": pass_name,
                "model": model,
                "temperature": temperature,
                "seed": seed,
                "thinking_level": resolved_thinking,
                "media_resolution": resolved_media_res,
                "prompt_tokens": prompt_tokens,
                "candidates_tokens": cand_tokens,
                "latency_s": round(latency, 3),
                "finish_reason": finish_reason,
            }
            log_call(self.log_path, record)

        return response
