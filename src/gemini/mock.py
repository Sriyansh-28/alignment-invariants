"""Deterministic offline provider used for testing the pipeline.

This exists so that the runner, metrics, statistics, and report generation can
be exercised end to end without a key and without spending API budget. It is a
*plumbing* fixture, not a model: numbers produced from it are never presented
as experimental results, and the runner stamps every output file with
``provider: "mock"`` so mock output cannot be mistaken for real output.
"""

from __future__ import annotations

import hashlib

from src.gemini.client import CallResult


class MockProvider:
    """Answers deterministically from a hash of the prompt.

    Behaviour is designed to exercise every branch the analysis handles:
    correct answers, wrong answers, format violations, answer changes across
    stages, and occasional unparseable replies.
    """

    def __init__(self, correct_answer_lookup: dict[str, str] | None = None,
                 accuracy: float = 0.65, malformed_rate: float = 0.04) -> None:
        self.lookup = correct_answer_lookup or {}
        self.accuracy = accuracy
        self.malformed_rate = malformed_rate
        self.calls = 0

    @staticmethod
    def _u(seed: str) -> float:
        h = hashlib.sha256(seed.encode("utf-8")).digest()
        return int.from_bytes(h[:4], "big") / 0xFFFFFFFF

    def generate(self, *, model: str, prompt: str, system: str | None,
                 temperature: float, max_output_tokens: int, seed: int | None,
                 thinking_budget: int | None) -> CallResult:
        self.calls += 1
        key = f"{model}|{prompt}|{system}|{seed}"
        u = self._u(key)

        if u < self.malformed_rate:
            return CallResult(text="I am not sure how to format this.",
                              from_cache=False, ok=True,
                              prompt_tokens=100, output_tokens=12)

        truth = None
        for task_text, ans in self.lookup.items():
            if task_text in prompt:
                truth = ans
                break

        answer = truth if (truth is not None and u < self.accuracy) else str(int(u * 90) + 3)
        wants_assessment = bool(system and "ASSESSMENT" in system)
        conf = 70 + int(self._u(key + "conf") * 30)

        lines = ["Working through the problem."]
        if wants_assessment:
            lines.append("ASSESSMENT: " + ("CORRECT" if u < 0.6 else "INCORRECT"))
        lines.append(f"FINAL: {answer}")
        lines.append(f"CONFIDENCE: {conf}")
        return CallResult(text="\n".join(lines), from_cache=False, ok=True,
                          prompt_tokens=120, output_tokens=25,
                          total_tokens=145, finish_reason="STOP")
