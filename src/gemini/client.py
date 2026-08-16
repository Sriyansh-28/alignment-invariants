"""Gemini client with a hard call budget, caching, and failure handling.

Budget discipline is a first-class concern here, not an afterthought. The
experiment is designed to run on Google's free tier, where the daily
request quota is small and changes without notice. Two independent guards
apply:

1. ``BudgetGuard`` refuses to issue call N+1 once N live calls have been made.
   Cache hits are free and never counted.
2. The runner plans the full call schedule *before* issuing any request and
   aborts if the plan would exceed the budget.

The API key is read from the environment, never logged, never written to the
cache, and never included in any serialized record.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.caching.cache import ResponseCache


class BudgetExceededError(RuntimeError):
    """Raised when a live call would exceed the configured hard cap."""


class APIKeyError(RuntimeError):
    """Raised when the key is missing or rejected by the service."""


@dataclass
class CallResult:
    text: str
    from_cache: bool
    ok: bool
    error: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    attempts: int = 1


@dataclass
class BudgetGuard:
    """Hard ceiling on live API calls. Cache hits do not count."""

    max_calls: int
    live_calls: int = 0
    successful: int = 0
    failed: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    per_condition: dict[str, int] = field(default_factory=dict)

    def check(self, n: int = 1) -> None:
        if self.live_calls + n > self.max_calls:
            raise BudgetExceededError(
                f"refusing call: {self.live_calls} live calls already made, "
                f"hard cap is {self.max_calls}"
            )

    def remaining(self) -> int:
        return self.max_calls - self.live_calls

    def record(self, result: CallResult, condition: str) -> None:
        if result.from_cache:
            self.cache_hits += 1
            return
        self.live_calls += 1
        self.per_condition[condition] = self.per_condition.get(condition, 0) + 1
        if result.ok:
            self.successful += 1
        else:
            self.failed += 1
        self.prompt_tokens += result.prompt_tokens or 0
        self.output_tokens += result.output_tokens or 0

    def summary(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "live_calls": self.live_calls,
            "successful_calls": self.successful,
            "failed_calls": self.failed,
            "cache_hits": self.cache_hits,
            "remaining": self.remaining(),
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.prompt_tokens + self.output_tokens,
            "calls_per_condition": dict(sorted(self.per_condition.items())),
        }


class Provider(Protocol):
    """Minimal surface the runner depends on, so it can be mocked in tests."""

    def generate(self, *, model: str, prompt: str, system: str | None,
                 temperature: float, max_output_tokens: int, seed: int | None,
                 thinking_budget: int | None) -> CallResult: ...


class GeminiProvider:
    """Thin wrapper over google-genai with retry and error classification."""

    def __init__(self, api_key: str, timeout_s: float = 60.0) -> None:
        if not api_key or not api_key.strip():
            raise APIKeyError(
                "GEMINI_API_KEY is empty or unset. Copy .env.example to .env "
                "and set a key from https://aistudio.google.com/apikey"
            )
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("google-genai is not installed; pip install -r requirements.txt") from exc
        self._genai = genai
        self._types = genai_types
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=int(timeout_s * 1000)),
        )

    @staticmethod
    def _classify(exc: Exception) -> tuple[str, bool]:
        """Return (error_kind, is_retryable). Never include response bodies that
        could echo the key back into logs."""
        name = type(exc).__name__
        msg = str(exc)
        low = msg.lower()
        if "api key not valid" in low or "api_key_invalid" in low or "unauthenticated" in low:
            return ("invalid_api_key", False)
        if "permission" in low or "403" in low:
            return ("permission_denied", False)
        if "429" in low or "resource_exhausted" in low or "quota" in low or "rate limit" in low:
            return ("rate_limited", True)
        if "503" in low or "unavailable" in low or "overloaded" in low:
            return ("service_unavailable", True)
        if "500" in low or "internal" in low:
            return ("server_error", True)
        if "timeout" in low or "deadline" in low:
            return ("timeout", True)
        return (f"unknown:{name}", True)

    def generate(self, *, model: str, prompt: str, system: str | None,
                 temperature: float, max_output_tokens: int, seed: int | None,
                 thinking_budget: int | None,
                 max_retries: int = 4, base_delay: float = 2.0) -> CallResult:
        cfg_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if system:
            cfg_kwargs["system_instruction"] = system
        if seed is not None:
            cfg_kwargs["seed"] = seed
        if thinking_budget is not None:
            cfg_kwargs["thinking_config"] = self._types.ThinkingConfig(
                thinking_budget=thinking_budget
            )
        config = self._types.GenerateContentConfig(**cfg_kwargs)

        last_error = "unknown"
        for attempt in range(1, max_retries + 1):
            try:
                resp = self._client.models.generate_content(
                    model=model, contents=prompt, config=config
                )
            except Exception as exc:  # noqa: BLE001 - classified below
                kind, retryable = self._classify(exc)
                last_error = kind
                if kind == "invalid_api_key":
                    # Fail loudly and immediately; retrying cannot help and
                    # would burn wall-clock time for every remaining item.
                    raise APIKeyError("Gemini rejected the API key (api_key_invalid).") from None
                if not retryable or attempt == max_retries:
                    return CallResult(text="", from_cache=False, ok=False,
                                      error=kind, attempts=attempt)
                # exponential backoff with jitter; rate limits are the common case
                delay = base_delay * (2 ** (attempt - 1))
                time.sleep(delay + random.uniform(0, 0.5 * delay))
                continue

            text = (getattr(resp, "text", None) or "").strip()
            usage = getattr(resp, "usage_metadata", None)
            p_tok = getattr(usage, "prompt_token_count", None) if usage else None
            o_tok = getattr(usage, "candidates_token_count", None) if usage else None
            t_tok = getattr(usage, "total_token_count", None) if usage else None
            finish = None
            cands = getattr(resp, "candidates", None)
            if cands:
                finish = str(getattr(cands[0], "finish_reason", None))

            if not text:
                # Empty completions happen on safety blocks and on
                # MAX_TOKENS truncation with thinking models. Treated as a
                # failed call, recorded, and NOT retried: a retry would spend
                # budget on a request that is deterministic at temperature 0.
                return CallResult(text="", from_cache=False, ok=False,
                                  error=f"empty_response(finish={finish})",
                                  prompt_tokens=p_tok, output_tokens=o_tok,
                                  total_tokens=t_tok, finish_reason=finish,
                                  attempts=attempt)

            return CallResult(text=text, from_cache=False, ok=True,
                              prompt_tokens=p_tok, output_tokens=o_tok,
                              total_tokens=t_tok, finish_reason=finish,
                              attempts=attempt)

        return CallResult(text="", from_cache=False, ok=False,
                          error=last_error, attempts=max_retries)


class CachedModel:
    """Cache-first wrapper that enforces the budget on every live call."""

    def __init__(self, provider: Provider | None, cache: ResponseCache,
                 guard: BudgetGuard, model: str, *, offline: bool = False,
                 namespace: str = "gemini") -> None:
        self.provider = provider
        self.cache = cache
        self.guard = guard
        self.model = model
        self.offline = offline
        # The namespace partitions the cache by provider. Without it, a run
        # against the mock provider would write entries under keys that a
        # later real run would read back, silently substituting synthetic
        # output for model output.
        self.namespace = namespace

    def call(self, *, prompt: str, system: str | None, temperature: float,
             max_output_tokens: int, seed: int | None, thinking_budget: int | None,
             condition: str, rep: int = 0) -> CallResult:
        request = {
            "namespace": self.namespace,
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "seed": seed,
            "thinking_budget": thinking_budget,
            "rep": rep,
        }
        key = self.cache.make_key(request)
        cached = self.cache.get(key)
        if cached is not None:
            result = CallResult(
                text=cached.get("text", ""),
                from_cache=True,
                ok=cached.get("ok", False),
                error=cached.get("error"),
                prompt_tokens=cached.get("prompt_tokens"),
                output_tokens=cached.get("output_tokens"),
                total_tokens=cached.get("total_tokens"),
                finish_reason=cached.get("finish_reason"),
            )
            self.guard.record(result, condition)
            return result

        if self.offline or self.provider is None:
            raise RuntimeError(
                "offline mode: cache miss with no provider available. "
                "Set GEMINI_API_KEY to make live calls, or run with a cache "
                "that already covers this experiment."
            )

        self.guard.check(1)
        result = self.provider.generate(
            model=self.model, prompt=prompt, system=system,
            temperature=temperature, max_output_tokens=max_output_tokens,
            seed=seed, thinking_budget=thinking_budget,
        )
        self.guard.record(result, condition)

        # Cache successes and hard failures alike. Caching a failure prevents a
        # re-run from silently re-spending budget on a request that already
        # failed deterministically; failures are visible in the results file.
        self.cache.put(key, {
            "text": result.text, "ok": result.ok, "error": result.error,
            "prompt_tokens": result.prompt_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
            "finish_reason": result.finish_reason,
            "request": {k: v for k, v in request.items() if k != "prompt"},
            "prompt_sha256": ResponseCache.make_key({"p": prompt}),
        })
        return result


def load_api_key() -> str | None:
    """Read the key from the environment. Returns None if absent."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key or None
