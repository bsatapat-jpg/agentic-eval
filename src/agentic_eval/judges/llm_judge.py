"""LLM-as-a-judge evaluator supporting OpenAI and Anthropic."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JudgeResult:
    """Result from an LLM judge evaluation."""

    score: float
    reason: str
    model: str = ""
    raw_response: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMJudge:
    """LLM-as-a-judge for evaluating agent behavior.

    Supports OpenAI and Anthropic APIs. Falls back gracefully
    if neither is available.

    Usage:
        judge = LLMJudge(provider="openai", model="gpt-4o-mini")
        result = judge.evaluate("Is this output correct? ...")
    """

    SCORE_EXTRACTION_PATTERN = re.compile(
        r"(?:score|rating)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*/?\s*(?:10|1\.0|1)?",
        re.IGNORECASE,
    )

    SYSTEM_PROMPT = (
        "You are an expert evaluator for AI agent behavior. "
        "When asked to evaluate, respond with a JSON object containing:\n"
        '- "score": a float between 0.0 and 1.0\n'
        '- "reason": a brief explanation for the score\n\n'
        "Be precise and objective. Base your evaluation only on the evidence provided."
    )

    def __init__(
        self,
        provider: str = "openai",
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.provider = provider
        self.temperature = temperature

        if provider == "openai":
            self.model = model or "gpt-4o-mini"
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        elif provider == "anthropic":
            self.model = model or "claude-sonnet-4-20250514"
            self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        else:
            self.model = model or "unknown"
            self.api_key = api_key

    def evaluate(self, prompt: str) -> JudgeResult:
        """Evaluate a prompt using the configured LLM."""
        if self.provider == "openai":
            return self._evaluate_openai(prompt)
        elif self.provider == "anthropic":
            return self._evaluate_anthropic(prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _evaluate_openai(self, prompt: str) -> JudgeResult:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content or ""
            return self._parse_response(raw)

        except ImportError:
            raise ImportError(
                "OpenAI package not installed. Install with: pip install agentic-eval[llm]"
            )

    def _evaluate_anthropic(self, prompt: str) -> JudgeResult:
        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
            )

            raw = response.content[0].text if response.content else ""
            return self._parse_response(raw)

        except ImportError:
            raise ImportError(
                "Anthropic package not installed. Install with: pip install agentic-eval[llm]"
            )

    def _parse_response(self, raw: str) -> JudgeResult:
        """Parse the LLM response into a JudgeResult."""
        try:
            json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                score = float(data.get("score", 0.0))
                if score > 1.0:
                    score = score / 10.0
                score = max(0.0, min(1.0, score))
                return JudgeResult(
                    score=score,
                    reason=data.get("reason", ""),
                    model=self.model,
                    raw_response=raw,
                )
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        match = self.SCORE_EXTRACTION_PATTERN.search(raw)
        if match:
            score = float(match.group(1))
            if score > 1.0:
                score = score / 10.0
            return JudgeResult(
                score=max(0.0, min(1.0, score)),
                reason=raw[:500],
                model=self.model,
                raw_response=raw,
            )

        return JudgeResult(
            score=0.5,
            reason=f"Could not parse LLM response: {raw[:200]}",
            model=self.model,
            raw_response=raw,
        )
