"""Output Correctness metric -- is the result right, not just 'done'?"""

from __future__ import annotations

import json
from typing import Any, Callable

from ..models import MetricResult, SkillSpec, Trace
from .base import BaseMetric


class OutputCorrectnessMetric(BaseMetric):
    """Validates the agent's output against expected content, schema, or assertions.

    Supports multiple validation modes:
    - Exact match (string comparison)
    - Contains check (substring)
    - Schema validation (dict structure)
    - Custom assertions (callable)
    """

    name = "output_correctness"
    description = "Is the result right, not just done?"
    tier = 1

    def __init__(self, assertions: list[Callable] | None = None) -> None:
        self._assertions = assertions or []

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        actual = trajectory.output

        if actual is None:
            return MetricResult(
                metric_name=self.name,
                score=0.0,
                passed=False,
                reason="No output produced",
            )

        if expected_output is None and not self._assertions:
            if skill_spec and skill_spec.output_schema:
                return self._validate_schema(actual, skill_spec.output_schema)
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="Output produced (no expected output to compare against)",
                details={"output_type": type(actual).__name__},
            )

        scores: list[float] = []
        details: dict[str, Any] = {}

        if expected_output is not None:
            match_score, match_details = self._compare_outputs(actual, expected_output)
            scores.append(match_score)
            details["output_match"] = match_details

        if skill_spec and skill_spec.output_schema:
            schema_score, schema_details = self._validate_schema_result(
                actual, skill_spec.output_schema
            )
            scores.append(schema_score)
            details["schema_validation"] = schema_details

        for i, assertion in enumerate(self._assertions):
            try:
                result = assertion(actual)
                passed = bool(result) if result is not None else True
                scores.append(1.0 if passed else 0.0)
                details[f"assertion_{i}"] = {"passed": passed}
            except Exception as exc:
                scores.append(0.0)
                details[f"assertion_{i}"] = {"passed": False, "error": str(exc)}

        overall = sum(scores) / len(scores) if scores else 0.0

        return MetricResult(
            metric_name=self.name,
            score=overall,
            passed=overall >= 0.5,
            reason=self._build_reason(overall, details),
            details=details,
        )

    def _compare_outputs(self, actual: Any, expected: Any) -> tuple[float, dict]:
        if isinstance(actual, str) and isinstance(expected, str):
            actual_norm = actual.strip().lower()
            expected_norm = expected.strip().lower()

            if actual_norm == expected_norm:
                return 1.0, {"match_type": "exact", "matched": True}

            if expected_norm in actual_norm:
                ratio = len(expected_norm) / len(actual_norm)
                return min(0.9, 0.5 + ratio * 0.4), {
                    "match_type": "contains",
                    "matched": True,
                }

            common_words = set(actual_norm.split()) & set(expected_norm.split())
            total_words = set(expected_norm.split())
            if total_words:
                overlap = len(common_words) / len(total_words)
                return overlap * 0.7, {
                    "match_type": "word_overlap",
                    "overlap_ratio": overlap,
                }

            return 0.0, {"match_type": "none", "matched": False}

        if actual == expected:
            return 1.0, {"match_type": "exact", "matched": True}

        if isinstance(actual, dict) and isinstance(expected, dict):
            return self._compare_dicts(actual, expected)

        return 0.0, {"match_type": "type_mismatch", "matched": False}

    def _compare_dicts(self, actual: dict, expected: dict) -> tuple[float, dict]:
        expected_keys = set(expected.keys())
        actual_keys = set(actual.keys())

        if not expected_keys:
            return 1.0, {"match_type": "dict", "matched": True}

        matching_keys = expected_keys & actual_keys
        matching_values = sum(
            1 for k in matching_keys if actual.get(k) == expected.get(k)
        )

        key_score = len(matching_keys) / len(expected_keys)
        value_score = matching_values / len(expected_keys) if expected_keys else 1.0
        overall = (key_score + value_score) / 2

        return overall, {
            "match_type": "dict",
            "key_coverage": key_score,
            "value_match": value_score,
            "missing_keys": list(expected_keys - actual_keys),
        }

    def _validate_schema(self, actual: Any, schema: dict) -> MetricResult:
        score, details = self._validate_schema_result(actual, schema)
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 0.5,
            reason=f"Schema validation: {'passed' if score >= 0.5 else 'failed'}",
            details=details,
        )

    def _validate_schema_result(self, actual: Any, schema: dict) -> tuple[float, dict]:
        if not isinstance(actual, dict):
            try:
                if isinstance(actual, str):
                    actual = json.loads(actual)
                else:
                    return 0.5, {"message": "Output is not a dict, cannot validate schema"}
            except (json.JSONDecodeError, TypeError):
                return 0.5, {"message": "Output is not JSON-parseable"}

        required_fields = schema.get("required", list(schema.get("properties", {}).keys()))
        if not required_fields:
            return 1.0, {"message": "No required fields in schema"}

        present = sum(1 for f in required_fields if f in actual)
        score = present / len(required_fields)

        return score, {
            "required_fields": required_fields,
            "present": present,
            "missing": [f for f in required_fields if f not in actual],
        }

    def _build_reason(self, score: float, details: dict) -> str:
        if score >= 0.9:
            return "Output is correct and matches expectations"
        if score >= 0.5:
            return "Output partially matches expectations"
        return "Output does not match expectations"
