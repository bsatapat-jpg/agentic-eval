"""Action Economy metric -- is the agent wasting steps?"""

from __future__ import annotations

from typing import Any

from ..models import MetricResult, SkillSpec, Trace
from .base import BaseMetric


class ActionEconomyMetric(BaseMetric):
    """Measures efficiency: actual steps vs optimal steps.

    The optimal step count is derived from the skill spec's required steps.
    If not available, uses a heuristic based on task complexity.
    """

    name = "action_economy"
    description = "Actual steps / optimal steps ratio"
    tier = 3

    def __init__(self, optimal_steps: int | None = None) -> None:
        self._optimal_steps = optimal_steps

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        actual_steps = self._count_actual_steps(trajectory)

        optimal = self._optimal_steps
        if optimal is None and skill_spec:
            required_steps = [s for s in skill_spec.steps if s.required]
            optimal = len(required_steps) if required_steps else None

        if optimal is None or optimal == 0:
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason=f"Cannot assess efficiency without optimal step count ({actual_steps} steps taken)",
                details={"actual_steps": actual_steps, "optimal_steps": None},
            )

        if actual_steps == 0:
            return MetricResult(
                metric_name=self.name,
                score=0.0,
                passed=False,
                reason="No steps taken",
                details={"actual_steps": 0, "optimal_steps": optimal},
            )

        ratio = optimal / actual_steps
        score = min(1.0, ratio)

        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 0.4,
            reason=self._build_reason(actual_steps, optimal, score),
            details={
                "actual_steps": actual_steps,
                "optimal_steps": optimal,
                "efficiency_ratio": round(ratio, 3),
            },
        )

    def _count_actual_steps(self, trajectory: Trace) -> int:
        """Count meaningful action steps (tool calls + agent steps)."""
        count = 0
        for span in trajectory.spans:
            count += self._count_span_steps(span)
        return count

    def _count_span_steps(self, span) -> int:
        count = 0
        if span.tool_call or span.type.value in ("tool_call", "agent_step"):
            count = 1
        for child in span.children:
            count += self._count_span_steps(child)
        return count

    def _build_reason(self, actual: int, optimal: int, score: float) -> str:
        if score >= 0.9:
            return f"Highly efficient: {actual} steps taken vs {optimal} optimal"
        if score >= 0.6:
            return f"Reasonably efficient: {actual} steps taken vs {optimal} optimal ({score:.0%} efficiency)"
        return f"Inefficient: {actual} steps taken vs {optimal} optimal ({score:.0%} efficiency)"
