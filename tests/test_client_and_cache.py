"""Caching, budget enforcement, and API failure handling.

Covers the operational requirements: invalid keys, rate limits, timeouts,
empty responses, and the guarantee that the hard call cap cannot be crossed.
No network access is used anywhere in this file.
"""

from __future__ import annotations

import json

import pytest

from src.caching.cache import ResponseCache
from src.gemini.client import (APIKeyError, BudgetExceededError, BudgetGuard,
                               CachedModel, CallResult, GeminiProvider)


class FakeProvider:
    """Records calls and returns a scripted result."""

    def __init__(self, result: CallResult | None = None):
        self.calls = 0
        self.result = result or CallResult(text="FINAL: 1\nCONFIDENCE: 50",
                                           from_cache=False, ok=True,
                                           prompt_tokens=10, output_tokens=5)

    def generate(self, **kwargs):
        self.calls += 1
        return self.result


def make_model(tmp_path, provider=None, max_calls=10, namespace="gemini"):
    cache = ResponseCache(tmp_path / "cache")
    guard = BudgetGuard(max_calls=max_calls)
    return CachedModel(provider or FakeProvider(), cache, guard,
                       "test-model", namespace=namespace), guard, cache


CALL = dict(prompt="p", system="s", temperature=0.0, max_output_tokens=64,
            seed=1, thinking_budget=0, condition="baseline")


class TestCache:
    def test_second_identical_call_is_served_from_cache(self, tmp_path):
        model, guard, _ = make_model(tmp_path)
        model.call(**CALL)
        model.call(**CALL)
        assert model.provider.calls == 1
        assert guard.live_calls == 1
        assert guard.cache_hits == 1

    def test_different_prompt_is_a_new_call(self, tmp_path):
        model, guard, _ = make_model(tmp_path)
        model.call(**CALL)
        model.call(**{**CALL, "prompt": "different"})
        assert guard.live_calls == 2

    def test_repetition_index_defeats_the_cache(self, tmp_path):
        """The consistency probe depends on rep=1 not colliding with rep=0."""
        model, guard, _ = make_model(tmp_path)
        model.call(**CALL, rep=0)
        model.call(**CALL, rep=1)
        assert guard.live_calls == 2

    def test_namespace_isolates_mock_from_real(self, tmp_path):
        """A mock run must never populate cache entries a real run would read."""
        cache = ResponseCache(tmp_path / "cache")
        guard = BudgetGuard(max_calls=10)
        mock_model = CachedModel(FakeProvider(), cache, guard, "m", namespace="mock")
        real_provider = FakeProvider()
        real_model = CachedModel(real_provider, cache, guard, "m", namespace="gemini")
        mock_model.call(**CALL)
        real_model.call(**CALL)
        assert real_provider.calls == 1, "real run wrongly served from mock cache"

    def test_key_material_never_enters_the_cache_key(self):
        a = ResponseCache.make_key({"prompt": "x", "api_key": "SECRET"})
        b = ResponseCache.make_key({"prompt": "x"})
        assert a == b

    def test_corrupt_entry_is_treated_as_a_miss(self, tmp_path):
        model, guard, cache = make_model(tmp_path)
        model.call(**CALL)
        # corrupt every stored entry
        for p in (tmp_path / "cache").rglob("*.json"):
            p.write_text("{not valid json", encoding="utf-8")
        model.call(**CALL)
        assert model.provider.calls == 2

    def test_no_secret_written_to_disk(self, tmp_path):
        model, _, _ = make_model(tmp_path)
        model.call(**CALL)
        for p in (tmp_path / "cache").rglob("*.json"):
            blob = json.loads(p.read_text(encoding="utf-8"))
            assert "api_key" not in json.dumps(blob).lower()


class TestFailuresAreNeverCached:
    """Regression cover for the Pilot 2 defect.

    Failures used to be written to the cache and replayed as ordinary hits, so a
    rerun after a bad run (expired key, transient 5xx, a retired model) served
    those failures as if they were model output -- with no live call and no
    budget spent to reveal the problem. The bug was dormant in Pilots 1 and 2
    only because every call happened to succeed."""

    def test_failed_response_is_not_written(self, tmp_path):
        fail = CallResult(text="", from_cache=False, ok=False, error="boom")
        model, guard, cache = make_model(tmp_path, FakeProvider(fail))
        model.call(**CALL)
        assert cache.writes == 0
        assert cache.stats()["rejected_failure_writes"] == 1
        assert not list((tmp_path / "cache").rglob("*.json"))

    def test_failed_call_is_reissued_not_replayed(self, tmp_path):
        """The second attempt must hit the provider again, not the cache."""
        provider = FakeProvider(CallResult(text="", from_cache=False, ok=False,
                                           error="boom"))
        model, guard, cache = make_model(tmp_path, provider)
        model.call(**CALL)
        model.call(**CALL)
        assert provider.calls == 2, "a cached failure was replayed"
        assert cache.hits == 0

    def test_stale_ok_false_entry_is_treated_as_a_miss(self, tmp_path):
        """An entry left on disk by an older revision must not be served."""
        cache = ResponseCache(tmp_path / "cache")
        key = "deadbeef" * 8
        # Write directly, bypassing put(), exactly as the old revision would have.
        p = cache._path(key)
        p.write_text(json.dumps({"text": "poison", "ok": False,
                                 "error": "404 NOT_FOUND"}), encoding="utf-8")
        assert cache.get(key) is None
        assert cache.stats()["stale_failure_entries"] == 1
        assert cache.hits == 0 and cache.misses == 1

    def test_successful_entry_is_still_cached(self, tmp_path):
        """The fix must not disable caching for the calls that matter."""
        provider = FakeProvider()
        model, guard, cache = make_model(tmp_path, provider)
        model.call(**CALL)
        model.call(**CALL)
        assert provider.calls == 1
        assert cache.hits == 1 and cache.writes == 1


class TestBudget:
    def test_hard_cap_blocks_the_next_call(self, tmp_path):
        model, guard, _ = make_model(tmp_path, max_calls=2)
        model.call(**CALL, rep=0)
        model.call(**CALL, rep=1)
        with pytest.raises(BudgetExceededError):
            model.call(**CALL, rep=2)
        assert guard.live_calls == 2

    def test_cache_hits_do_not_consume_budget(self, tmp_path):
        model, guard, _ = make_model(tmp_path, max_calls=1)
        model.call(**CALL)
        model.call(**CALL)   # cached; must not raise despite cap of 1
        model.call(**CALL)
        assert guard.live_calls == 1

    def test_failures_still_count_against_the_budget(self, tmp_path):
        """A failed call costs quota, so it must be counted or the cap leaks."""
        bad = CallResult(text="", from_cache=False, ok=False, error="server_error")
        model, guard, _ = make_model(tmp_path, provider=FakeProvider(bad))
        model.call(**CALL)
        assert guard.live_calls == 1 and guard.failed == 1 and guard.successful == 0

    def test_quota_failure_is_debited_before_the_run_stops(self, tmp_path):
        """Hitting the quota ends the session, but the request it took to find
        that out was still spent and must be on the books."""
        from src.gemini.client import QuotaExhaustedError
        bad = CallResult(text="", from_cache=False, ok=False,
                         error="rate_limited", attempts=4)
        model, guard, cache = make_model(tmp_path, provider=FakeProvider(bad))
        with pytest.raises(QuotaExhaustedError):
            model.call(**CALL)
        assert guard.live_calls == 1 and guard.failed == 1
        assert guard.api_requests == 4, "retried attempts were not charged"
        assert cache.writes == 0, "a quota failure was cached"

    def test_per_condition_accounting(self, tmp_path):
        model, guard, _ = make_model(tmp_path)
        model.call(**{**CALL, "condition": "baseline"})
        model.call(**{**CALL, "prompt": "q", "condition": "self_critique"})
        model.call(**{**CALL, "prompt": "r", "condition": "self_critique"})
        assert guard.summary()["calls_per_condition"] == {
            "baseline": 1, "self_critique": 2}

    def test_token_accounting(self, tmp_path):
        model, guard, _ = make_model(tmp_path)
        model.call(**CALL)
        s = guard.summary()
        assert s["prompt_tokens"] == 10 and s["output_tokens"] == 5
        assert s["total_tokens"] == 15


class TestOffline:
    def test_offline_cache_miss_raises(self, tmp_path):
        cache = ResponseCache(tmp_path / "cache")
        guard = BudgetGuard(max_calls=5)
        model = CachedModel(None, cache, guard, "m", offline=True)
        with pytest.raises(RuntimeError, match="offline"):
            model.call(**CALL)

    def test_offline_hit_works(self, tmp_path):
        cache = ResponseCache(tmp_path / "cache")
        guard = BudgetGuard(max_calls=5)
        CachedModel(FakeProvider(), cache, guard, "m").call(**CALL)
        offline = CachedModel(None, cache, guard, "m", offline=True)
        assert offline.call(**CALL).from_cache is True


class TestErrorClassification:
    @pytest.mark.parametrize("msg,kind,retryable", [
        ("API key not valid. Please pass a valid API key.", "invalid_api_key", False),
        ("429 RESOURCE_EXHAUSTED: quota exceeded", "rate_limited", True),
        ("503 Service Unavailable: model overloaded", "service_unavailable", True),
        ("Deadline exceeded / timeout", "timeout", True),
        ("500 Internal error", "server_error", True),
        ("403 permission denied", "permission_denied", False),
    ])
    def test_classification(self, msg, kind, retryable):
        assert GeminiProvider._classify(Exception(msg)) == (kind, retryable)

    def test_empty_key_rejected_without_network(self):
        with pytest.raises(APIKeyError):
            GeminiProvider("")
        with pytest.raises(APIKeyError):
            GeminiProvider("   ")


class TestRetryBehaviour:
    def test_rate_limit_is_retried_then_gives_up(self, monkeypatch):
        """Retries must back off and eventually return a failed CallResult
        rather than looping forever."""
        provider = GeminiProvider.__new__(GeminiProvider)  # bypass __init__/network
        attempts = {"n": 0}

        class Boom:
            def generate_content(self, **kwargs):
                attempts["n"] += 1
                raise Exception("429 RESOURCE_EXHAUSTED")

        class C:
            models = Boom()

        provider._client = C()
        from google.genai import types as t
        provider._types = t
        monkeypatch.setattr("time.sleep", lambda *_: None)

        res = provider.generate(model="m", prompt="p", system=None, temperature=0.0,
                                max_output_tokens=16, seed=None, thinking_budget=0,
                                max_retries=3, base_delay=0.0)
        assert res.ok is False
        assert res.error == "rate_limited"
        assert attempts["n"] == 3

    def test_invalid_key_is_not_retried(self, monkeypatch):
        provider = GeminiProvider.__new__(GeminiProvider)
        attempts = {"n": 0}

        class Boom:
            def generate_content(self, **kwargs):
                attempts["n"] += 1
                raise Exception("API key not valid")

        class C:
            models = Boom()

        provider._client = C()
        from google.genai import types as t
        provider._types = t
        monkeypatch.setattr("time.sleep", lambda *_: None)

        with pytest.raises(APIKeyError):
            provider.generate(model="m", prompt="p", system=None, temperature=0.0,
                              max_output_tokens=16, seed=None, thinking_budget=0)
        assert attempts["n"] == 1, "an invalid key must fail fast, not retry"

    def test_empty_response_is_recorded_as_failure(self, monkeypatch):
        provider = GeminiProvider.__new__(GeminiProvider)

        class Resp:
            text = "   "
            usage_metadata = None
            candidates = []

        class Models:
            def generate_content(self, **kwargs):
                return Resp()

        class C:
            models = Models()

        provider._client = C()
        from google.genai import types as t
        provider._types = t

        res = provider.generate(model="m", prompt="p", system=None, temperature=0.0,
                                max_output_tokens=16, seed=None, thinking_budget=0)
        assert res.ok is False and "empty_response" in res.error
