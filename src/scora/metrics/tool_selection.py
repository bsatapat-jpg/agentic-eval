"""Tool Selection Accuracy metric -- is the agent picking the right tools?"""

from __future__ import annotations

from typing import Any

from ..models import MetricResult, SkillSpec, Trace
from .base import BaseMetric


class ToolSelectionMetric(BaseMetric):
    """Measures whether the agent selected the correct tools as prescribed.

    Evaluates:
    - Precision: what fraction of tools used were expected?
    - Recall: what fraction of expected tools were used?
    - F1: harmonic mean of precision and recall
    """

    name = "tool_selection"
    description = "Percentage of tool calls matching prescribed tools"
    tier = 2

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        expected_tools = set()
        if skill_spec:
            expected_tools.update(skill_spec.expected_tools)
            for step in skill_spec.steps:
                expected_tools.update(step.expected_tools)

        if not expected_tools:
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="No expected tools defined in skill spec",
            )

        actual_calls = trajectory.tool_calls
        actual_tool_names = [tc.name for tc in actual_calls]
        actual_tools_set = set(actual_tool_names)

        if not actual_tools_set:
            return MetricResult(
                metric_name=self.name,
                score=0.0,
                passed=False,
                reason="No tools were called by the agent",
                details={
                    "expected": sorted(expected_tools),
                    "actual": [],
                    "precision": 0.0,
                    "recall": 0.0,
                },
            )

        true_positives = actual_tools_set & expected_tools
        false_positives = actual_tools_set - expected_tools
        false_negatives = expected_tools - actual_tools_set

        precision = len(true_positives) / len(actual_tools_set) if actual_tools_set else 0.0
        recall = len(true_positives) / len(expected_tools) if expected_tools else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        call_level_accuracy = sum(
            1 for tc in actual_calls if tc.name in expected_tools
        ) / len(actual_calls) if actual_calls else 0.0

        overall = (f1 + call_level_accuracy) / 2

        return MetricResult(
            metric_name=self.name,
            score=overall,
            passed=overall >= 0.5,
            reason=self._build_reason(precision, recall, false_positives, false_negatives),
            details={
                "expected": sorted(expected_tools),
                "actual": sorted(actual_tools_set),
                "true_positives": sorted(true_positives),
                "false_positives": sorted(false_positives),
                "false_negatives": sorted(false_negatives),
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
                "call_level_accuracy": round(call_level_accuracy, 3),
            },
        )

    def _build_reason(
        self,
        precision: float,
        recall: float,
        false_positives: set,
        false_negatives: set,
    ) -> str:
        parts: list[str] = []
        parts.append(f"Precision: {precision:.0%}, Recall: {recall:.0%}")
        if false_negatives:
            parts.append(f"Missing tools: {', '.join(sorted(false_negatives))}")
        if false_positives:
            parts.append(f"Unexpected tools: {', '.join(sorted(false_positives))}")
        return ". ".join(parts)
