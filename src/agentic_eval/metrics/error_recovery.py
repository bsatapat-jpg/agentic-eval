"""Error Recovery metric -- can the agent handle real-world messiness?"""

from __future__ import annotations

from typing import Any

from ..models import MetricResult, SkillSpec, SpanType, Trace
from .base import BaseMetric


class ErrorRecoveryMetric(BaseMetric):
    """Measures the agent's ability to recover from errors during execution.

    Evaluates:
    - Were there any errors?
    - After each error, did the agent continue and eventually produce output?
    - Did the agent retry failed operations?
    - Did the agent spiral (repeated identical errors)?
    """

    name = "error_recovery"
    description = "When a step fails, does the agent recover vs. spiral?"
    tier = 2

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        all_spans = self._flat_spans(trajectory)
        error_spans = [s for s in all_spans if s.error]

        if not error_spans:
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="No errors encountered -- nothing to recover from",
                details={"error_count": 0, "recovery_needed": False},
            )

        has_output = trajectory.output is not None and trajectory.output != ""
        total_errors = len(error_spans)

        spiral_detected = self._detect_spiral(error_spans)

        retries = self._detect_retries(all_spans)

        recovered_errors = 0
        for i, err_span in enumerate(error_spans):
            subsequent_spans = [
                s for s in all_spans
                if s.started_at > err_span.started_at and not s.error
            ]
            if subsequent_spans:
                recovered_errors += 1

        recovery_rate = recovered_errors / total_errors if total_errors else 0.0

        score_components: list[float] = [recovery_rate]

        if has_output:
            score_components.append(1.0)
        else:
            score_components.append(0.0)

        if spiral_detected:
            score_components.append(0.0)
        else:
            score_components.append(1.0)

        overall = sum(score_components) / len(score_components)

        return MetricResult(
            metric_name=self.name,
            score=overall,
            passed=overall >= 0.5,
            reason=self._build_reason(
                total_errors, recovered_errors, has_output, spiral_detected, retries
            ),
            details={
                "total_errors": total_errors,
                "recovered_errors": recovered_errors,
                "recovery_rate": round(recovery_rate, 3),
                "has_final_output": has_output,
                "spiral_detected": spiral_detected,
                "retry_count": retries,
                "error_messages": [s.error for s in error_spans],
            },
        )

    def _detect_spiral(self, error_spans: list) -> bool:
        """Detect if the agent is spiraling (repeating the same error 3+ times)."""
        if len(error_spans) < 3:
            return False

        error_messages = [s.error for s in error_spans]
        from collections import Counter

        counts = Counter(error_messages)
        return any(c >= 3 for c in counts.values())

    def _detect_retries(self, all_spans: list) -> int:
        """Count retry attempts (same tool called after an error)."""
        retries = 0
        error_tools: set[str] = set()

        for span in all_spans:
            if span.error and span.tool_call:
                error_tools.add(span.tool_call.name)
            elif span.tool_call and span.tool_call.name in error_tools and not span.error:
                retries += 1
                error_tools.discard(span.tool_call.name)

        return retries

    def _flat_spans(self, trajectory: Trace) -> list:
        result = []
        for span in trajectory.spans:
            result.append(span)
            self._collect_children(span, result)
        return result

    def _collect_children(self, span, result: list) -> None:
        for child in span.children:
            result.append(child)
            self._collect_children(child, result)

    def _build_reason(
        self,
        total_errors: int,
        recovered: int,
        has_output: bool,
        spiral: bool,
        retries: int,
    ) -> str:
        parts: list[str] = []
        parts.append(f"{total_errors} error(s) encountered")
        parts.append(f"{recovered} recovered")

        if spiral:
            parts.append("ERROR SPIRAL detected (repeated identical failures)")
        if retries:
            parts.append(f"{retries} successful retry(ies)")
        if has_output:
            parts.append("Final output produced despite errors")
        else:
            parts.append("No final output -- recovery failed")

        return ". ".join(parts)
