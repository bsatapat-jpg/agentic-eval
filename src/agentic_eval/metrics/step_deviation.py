"""Step Deviation metric -- where does the agent go off-track?"""

from __future__ import annotations

from typing import Any

from ..models import MetricResult, SkillSpec, Trace
from .base import BaseMetric


class StepDeviationMetric(BaseMetric):
    """Measures divergence between expected action sequence and actual trajectory.

    Computes the diff between the SKILL.md's defined steps and the agent's
    actual execution path, identifying insertions, deletions, and reorderings.
    """

    name = "step_deviation"
    description = "Diff between expected action sequence and actual trajectory"
    tier = 2

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        if skill_spec is None or not skill_spec.steps:
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="No expected steps defined -- nothing to deviate from",
            )

        expected_sequence = [s.description.lower() for s in skill_spec.steps]
        actual_sequence = self._extract_actual_sequence(trajectory)

        if not actual_sequence:
            return MetricResult(
                metric_name=self.name,
                score=0.0,
                passed=False,
                reason="No actions recorded in trajectory",
                details={"expected_steps": len(expected_sequence), "actual_steps": 0},
            )

        lcs_len = self._longest_common_subsequence_length(expected_sequence, actual_sequence)
        max_len = max(len(expected_sequence), len(actual_sequence))
        score = lcs_len / max_len if max_len > 0 else 1.0

        deviations = self._identify_deviations(expected_sequence, actual_sequence)

        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 0.5,
            reason=self._build_reason(score, deviations),
            details={
                "expected_steps": len(expected_sequence),
                "actual_steps": len(actual_sequence),
                "lcs_length": lcs_len,
                "deviations": deviations,
                "expected_sequence": expected_sequence,
                "actual_sequence": actual_sequence,
            },
        )

    def _extract_actual_sequence(self, trajectory: Trace) -> list[str]:
        """Extract a sequence of action descriptions from the trajectory."""
        actions: list[str] = []
        for span in trajectory.spans:
            self._collect_actions(span, actions)
        return actions

    def _collect_actions(self, span, actions: list[str]) -> None:
        if span.tool_call:
            actions.append(span.tool_call.name.lower())
        elif span.name:
            actions.append(span.name.lower())
        for child in span.children:
            self._collect_actions(child, actions)

    def _longest_common_subsequence_length(
        self, seq_a: list[str], seq_b: list[str]
    ) -> int:
        """Compute LCS length with fuzzy matching."""
        m, n = len(seq_a), len(seq_b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if self._fuzzy_match(seq_a[i - 1], seq_b[j - 1]):
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

        return dp[m][n]

    def _fuzzy_match(self, a: str, b: str) -> bool:
        """Check if two action descriptions are semantically similar."""
        if a == b:
            return True

        a_words = set(a.replace("_", " ").replace("-", " ").split())
        b_words = set(b.replace("_", " ").replace("-", " ").split())

        stop_words = {"the", "a", "an", "to", "and", "or", "of", "in", "for", "with"}
        a_words -= stop_words
        b_words -= stop_words

        if not a_words or not b_words:
            return False

        overlap = len(a_words & b_words) / max(len(a_words), len(b_words))
        return overlap >= 0.5

    def _identify_deviations(
        self, expected: list[str], actual: list[str]
    ) -> list[dict]:
        """Identify specific deviations between expected and actual sequences."""
        deviations: list[dict] = []

        expected_set = set(expected)
        actual_set = set(actual)

        for step in expected:
            if not any(self._fuzzy_match(step, a) for a in actual):
                deviations.append({
                    "type": "missing_step",
                    "description": f"Expected step not found: '{step}'",
                })

        for action in actual:
            if not any(self._fuzzy_match(action, e) for e in expected):
                deviations.append({
                    "type": "extra_step",
                    "description": f"Unexpected action: '{action}'",
                })

        return deviations

    def _build_reason(self, score: float, deviations: list[dict]) -> str:
        if score >= 0.9:
            return "Agent closely followed the expected step sequence"
        if score >= 0.5:
            missing = sum(1 for d in deviations if d["type"] == "missing_step")
            extra = sum(1 for d in deviations if d["type"] == "extra_step")
            parts = []
            if missing:
                parts.append(f"{missing} missing step(s)")
            if extra:
                parts.append(f"{extra} extra action(s)")
            return f"Moderate deviation: {', '.join(parts)}"
        return "Significant deviation from expected step sequence"
