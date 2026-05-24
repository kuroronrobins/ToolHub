"""LLM cost accounting helpers.

This module only stores request metadata and token/cost estimates. It must not
store prompt text, transcript text, API keys, or generated minutes bodies.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


@dataclass(frozen=True)
class ModelPricing:
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None = None


# Approximate built-in estimates used only when provider usage/cost is not
# available. Pricing changes; docs instruct users to verify current official
# prices before making default-setting decisions.
MODEL_PRICING_USD_PER_1M: dict[str, ModelPricing] = {
    "gpt-5.5": ModelPricing(input_per_1m=5.0, output_per_1m=30.0, cached_input_per_1m=0.50),
    "gpt-5.5-pro": ModelPricing(input_per_1m=30.0, output_per_1m=180.0),
    "gpt-5.4": ModelPricing(input_per_1m=2.5, output_per_1m=15.0, cached_input_per_1m=0.25),
    "gpt-5.4-pro": ModelPricing(input_per_1m=30.0, output_per_1m=180.0),
    "gpt-5.4-mini": ModelPricing(input_per_1m=0.75, output_per_1m=4.5, cached_input_per_1m=0.075),
    "gpt-5.4-nano": ModelPricing(input_per_1m=0.20, output_per_1m=1.25, cached_input_per_1m=0.02),
    "gpt-5.2": ModelPricing(input_per_1m=1.75, output_per_1m=14.0, cached_input_per_1m=0.175),
    "gpt-5.1": ModelPricing(input_per_1m=1.25, output_per_1m=10.0, cached_input_per_1m=0.125),
    "gpt-5": ModelPricing(input_per_1m=1.25, output_per_1m=10.0, cached_input_per_1m=0.125),
    "gpt-5-mini": ModelPricing(input_per_1m=0.25, output_per_1m=2.0, cached_input_per_1m=0.025),
    "gpt-5-nano": ModelPricing(input_per_1m=0.05, output_per_1m=0.40, cached_input_per_1m=0.005),
    "gpt-4o": ModelPricing(input_per_1m=2.5, output_per_1m=10.0, cached_input_per_1m=1.25),
    "gpt-4.1": ModelPricing(input_per_1m=2.0, output_per_1m=8.0, cached_input_per_1m=0.50),
    "gpt-4.1-mini": ModelPricing(input_per_1m=0.40, output_per_1m=1.60, cached_input_per_1m=0.10),
    "gpt-4.1-nano": ModelPricing(input_per_1m=0.10, output_per_1m=0.40, cached_input_per_1m=0.025),
    "gpt-4o-mini": ModelPricing(input_per_1m=0.15, output_per_1m=0.60, cached_input_per_1m=0.075),
}


MODEL_PRICING_UNKNOWN: set[str] = set()


def normalize_model_name(model: str) -> str:
    return str(model or "").strip().lower()


def pricing_for_model(model: str) -> ModelPricing | None:
    name = normalize_model_name(model)
    if name in MODEL_PRICING_UNKNOWN:
        return None
    if name in MODEL_PRICING_USD_PER_1M:
        return MODEL_PRICING_USD_PER_1M[name]
    for key in sorted(MODEL_PRICING_USD_PER_1M, key=len, reverse=True):
        pricing = MODEL_PRICING_USD_PER_1M[key]
        if name.startswith(key):
            return pricing
    return None


def estimate_tokens_from_chars(chars: int | float) -> int:
    """Estimate text tokens from character count for mixed Japanese/English text."""
    try:
        value = max(0, int(chars))
    except Exception:
        value = 0
    if value <= 0:
        return 0
    return int(math.ceil(value / 3.2))


def json_chars(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        return len(str(value or ""))


def payload_prompt_chars(payload: Mapping[str, Any]) -> int:
    if not isinstance(payload, Mapping):
        return json_chars(payload)
    if "input" in payload:
        return json_chars(payload.get("input"))
    if "messages" in payload:
        return json_chars(payload.get("messages"))
    return json_chars(payload)


def response_output_chars(response: Mapping[str, Any] | None) -> int:
    if not isinstance(response, Mapping):
        return 0
    output = response.get("output")
    if output is not None:
        return json_chars(output)
    choices = response.get("choices")
    if choices is not None:
        return json_chars(choices)
    return 0


def extract_usage_tokens(response_or_usage: Mapping[str, Any] | None) -> dict[str, int]:
    if not isinstance(response_or_usage, Mapping):
        return {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    usage = response_or_usage.get("usage") if "usage" in response_or_usage else response_or_usage
    if not isinstance(usage, Mapping):
        return {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}

    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    details = (
        usage.get("input_tokens_details")
        or usage.get("input_token_details")
        or usage.get("prompt_tokens_details")
        or {}
    )
    cached = 0
    if isinstance(details, Mapping):
        cached = int(details.get("cached_tokens") or details.get("cached_input_tokens") or 0)
    return {
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
        "cached_input_tokens": max(0, cached),
    }


def estimate_llm_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float:
    pricing = pricing_for_model(model)
    if pricing is None:
        return 0.0
    cached = min(max(0, int(cached_input_tokens)), max(0, int(input_tokens)))
    uncached = max(0, int(input_tokens) - cached)
    cached_rate = pricing.cached_input_per_1m
    if cached_rate is None:
        cached_rate = pricing.input_per_1m
    return (
        (uncached * pricing.input_per_1m)
        + (cached * cached_rate)
        + (max(0, int(output_tokens)) * pricing.output_per_1m)
    ) / 1_000_000.0


@dataclass
class LlmCostRecord:
    component: str
    model: str
    request_start_time: float
    request_elapsed_seconds: float
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    estimated_cost_usd: float
    session_id: str
    source: str
    prompt_chars: int
    output_chars: int
    success: bool
    failure: str = ""
    retry_count: int = 0
    pricing_basis: str = "usage_or_estimate"

    @classmethod
    def from_payload_response(
        cls,
        *,
        component: str,
        model: str,
        session_id: str,
        source: str,
        payload: Mapping[str, Any],
        response: Mapping[str, Any] | None,
        started_at: float,
        elapsed_seconds: float,
        success: bool,
        failure: str = "",
        retry_count: int = 0,
    ) -> "LlmCostRecord":
        prompt_chars = payload_prompt_chars(payload)
        output_chars = response_output_chars(response)
        usage = extract_usage_tokens(response)
        input_tokens = usage["input_tokens"] or estimate_tokens_from_chars(prompt_chars)
        output_tokens = usage["output_tokens"] or estimate_tokens_from_chars(output_chars)
        cached_input_tokens = usage["cached_input_tokens"]
        pricing_basis = "api_usage" if usage["input_tokens"] or usage["output_tokens"] else "char_estimate"
        if pricing_for_model(model) is None:
            pricing_basis = f"{pricing_basis}:unknown_model_price"
        return cls(
            component=str(component or "other"),
            model=str(model or ""),
            request_start_time=float(started_at),
            request_elapsed_seconds=max(0.0, float(elapsed_seconds)),
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cached_input_tokens=int(cached_input_tokens),
            estimated_cost_usd=estimate_llm_cost_usd(
                model=model,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                cached_input_tokens=int(cached_input_tokens),
            ),
            session_id=str(session_id or ""),
            source=str(source or ""),
            prompt_chars=int(prompt_chars),
            output_chars=int(output_chars),
            success=bool(success),
            failure=str(failure or "")[:240],
            retry_count=max(0, int(retry_count or 0)),
            pricing_basis=pricing_basis,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def append_cost_record_jsonl(path: str | Path, record: LlmCostRecord) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")))
        fh.write("\n")


def load_cost_records(path: str | Path) -> list[LlmCostRecord]:
    target = Path(path)
    if not target.exists():
        return []
    records: list[LlmCostRecord] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            records.append(LlmCostRecord(**data))
        except Exception:
            continue
    return records


def summarize_cost_records(
    records: Iterable[LlmCostRecord],
    *,
    session_duration_seconds: float | None = None,
) -> dict[str, Any]:
    recs = list(records)
    total_cost = sum(r.estimated_cost_usd for r in recs)
    total_input = sum(r.input_tokens for r in recs)
    total_output = sum(r.output_tokens for r in recs)

    def _group(key: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in recs:
            group = str(getattr(r, key) or "unknown")
            bucket = out.setdefault(
                group,
                {"requests": 0, "estimated_cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0},
            )
            bucket["requests"] += 1
            bucket["estimated_cost_usd"] += r.estimated_cost_usd
            bucket["input_tokens"] += r.input_tokens
            bucket["output_tokens"] += r.output_tokens
        return out

    hourly = None
    if session_duration_seconds and session_duration_seconds > 0:
        hourly = total_cost * 3600.0 / float(session_duration_seconds)

    by_component = _group("component")
    minutes_inc = by_component.get("minutes_incremental", {}).get("estimated_cost_usd", 0.0)
    minutes_final = by_component.get("minutes_final", {}).get("estimated_cost_usd", 0.0)
    stt = by_component.get("stt", {}).get("estimated_cost_usd", 0.0)
    minutes_total = minutes_inc + minutes_final
    return {
        "total_estimated_cost_usd": total_cost,
        "estimated_cost_per_hour_usd": hourly,
        "requests": len(recs),
        "successes": sum(1 for r in recs if r.success),
        "failures": sum(1 for r in recs if not r.success),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "by_component": by_component,
        "by_model": _group("model"),
        "top_expensive_calls": [
            r.to_dict()
            for r in sorted(recs, key=lambda item: item.estimated_cost_usd, reverse=True)[:5]
        ],
        "minutes_incremental_to_final_cost_ratio": (
            minutes_inc / minutes_final if minutes_final > 0 else None
        ),
        "stt_to_minutes_cost_ratio": stt / minutes_total if minutes_total > 0 else None,
    }


def now_epoch_seconds() -> float:
    return time.time()
