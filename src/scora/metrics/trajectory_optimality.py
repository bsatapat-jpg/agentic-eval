"""Trajectory Optimality metric -- is the agent's execution path
coherent, non-redundant, and logically ordered?

Goes beyond simple step counting (action_economy) to evaluate the
*quality* of the execution trajectory as a plan.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..models import MetricResult, SkillSpec, Span, SpanType, Trace
from .base import BaseMetric


class TrajectoryOptimalityMetric(BaseMetric):
    """Measures the quality of the agent's execution trajectory as a plan.

    Evaluates four dimensions beyond simple step counting:

    1. **Redundancy**: Are there repeated identical tool calls?
       Agents that call the same tool with the same args multiple times
       are wasting compute and latency.

    2. **Result Utilization**: Did the agent use the results of its
       tool calls? Calls whose results are never referenced downstream
       indicate poor planning.

    3. **Logical Ordering**: Are dependent steps in the right order?
       (e.g., search before use, read before write, validate before submit)

    4. **Backtracking**: Does the agent undo or redo its own work?
       Frequent backtracking signals poor planning.
    """

    name = "trajectory_optimality"
    description = "Is the trajectory coherent, non-redundant, and logically ordered?"
    tier = 2

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        all_spans = self._walk(trajectory.spans)
        tool_spans = [s for s in all_spans if s.tool_call or s.type == SpanType.TOOL_CALL]

        if len(tool_spans) < 2:
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="Too few tool calls to evaluate trajectory quality",
                details={"tool_call_count": len(tool_spans)},
            )

        redundancy_score, redundancy_details = self._evaluate_redundancy(tool_spans)
        utilization_score, utilization_details = self._evaluate_result_utilization(
            tool_spans, trajectory
        )
        ordering_score, ordering_details = self._evaluate_logical_ordering(tool_spans)
        backtrack_score, backtrack_details = self._evaluate_backtracking(tool_spans)

        overall = (
            redundancy_score * 0.30
            + utilization_score * 0.30
            + ordering_score * 0.20
            + backtrack_score * 0.20
        )

        return MetricResult(
            metric_name=self.name,
            score=round(overall, 4),
            passed=overall >= 0.5,
            reason=self._build_reason(
                redundancy_score, utilization_score, ordering_score, backtrack_score,
                redundancy_details, backtrack_details,
            ),
            details={
                "tool_call_count": len(tool_spans),
                "redundancy": redundancy_details,
                "result_utilization": utilization_details,
                "logical_ordering": ordering_details,
                "backtracking": backtrack_details,
                "scores": {
                    "redundancy": round(redundancy_score, 3),
                    "utilization": round(utilization_score, 3),
                    "ordering": round(ordering_score, 3),
                    "backtracking": round(backtrack_score, 3),
                },
            },
        )

    def _evaluate_redundancy(self, tool_spans: list[Span]) -> tuple[float, dict]:
        """Detect repeated identical tool calls (same name + same args)."""
        call_sigs: list[str] = []
        for span in tool_spans:
            tc = span.tool_call
            if tc:
                sig = f"{tc.name}:{_stable_repr(tc.arguments)}"
            else:
                sig = span.name
            call_sigs.append(sig)

        counts = Counter(call_sigs)
        total = len(call_sigs)
        unique = len(counts)
        duplicates = sum(max(0, c - 1) for c in counts.values())

        redundancy_ratio = duplicates / total if total > 0 else 0.0
        score = max(0.0, 1.0 - redundancy_ratio * 2)

        repeated_calls = {sig: cnt for sig, cnt in counts.items() if cnt > 1}

        return score, {
            "total_calls": total,
            "unique_calls": unique,
            "duplicate_calls": duplicates,
            "redundancy_ratio": round(redundancy_ratio, 3),
            "repeated": {k.split(":")[0]: v for k, v in repeated_calls.items()},
        }

    def _evaluate_result_utilization(
        self, tool_spans: list[Span], trajectory: Trace
    ) -> tuple[float, dict]:
        """Check if tool results were used downstream."""
        output_text = str(trajectory.output or "").lower()
        utilized = 0
        total_with_results = 0

        per_tool: list[dict] = []
        for span in tool_spans:
            result_text = self._get_result_text(span)
            if not result_text:
                continue

            total_with_results += 1
            result_tokens = self._extract_significant_tokens(result_text)

            used = False
            if result_tokens:
                output_tokens = set(output_text.split())
                overlap = result_tokens & output_tokens
                if len(overlap) >= min(3, len(result_tokens)):
                    used = True

            if not used:
                later_spans = tool_spans[tool_spans.index(span) + 1:]
                for later in later_spans:
                    later_input = str(later.tool_call.arguments if later.tool_call else later.input or "").lower()
                    later_tokens = set(later_input.split())
                    if result_tokens & later_tokens:
                        used = True
                        break

            if used:
                utilized += 1
            per_tool.append({
                "tool": span.tool_call.name if span.tool_call else span.name,
                "result_used": used,
            })

        score = utilized / total_with_results if total_with_results > 0 else 1.0

        return score, {
            "total_with_results": total_with_results,
            "results_utilized": utilized,
            "per_tool": per_tool,
        }

    def _evaluate_logical_ordering(self, tool_spans: list[Span]) -> tuple[float, dict]:
        """Check for logical ordering patterns (read→write, search→use, etc.)."""
        read_ops = {"read", "get", "fetch", "search", "query", "list", "find", "retrieve", "lookup"}
        write_ops = {"write", "create", "update", "delete", "set", "put", "post", "insert", "save", "submit"}
        validate_ops = {"validate", "check", "verify", "test", "assert", "confirm"}

        tool_names = [
            (span.tool_call.name if span.tool_call else span.name).lower().replace("_", " ")
            for span in tool_spans
        ]

        violations = 0
        checks = 0

        first_read = None
        first_write = None
        for i, name in enumerate(tool_names):
            name_words = set(name.split())
            is_read = bool(name_words & read_ops)
            is_write = bool(name_words & write_ops)

            if is_read and first_read is None:
                first_read = i
            if is_write and first_write is None:
                first_write = i

        if first_read is not None and first_write is not None:
            checks += 1
            if first_write < first_read:
                violations += 1

        first_validate = None
        first_submit = None
        for i, name in enumerate(tool_names):
            name_words = set(name.split())
            if name_words & validate_ops and first_validate is None:
                first_validate = i
            if name_words & {"submit", "send", "deploy", "publish"} and first_submit is None:
                first_submit = i

        if first_validate is not None and first_submit is not None:
            checks += 1
            if first_submit < first_validate:
                violations += 1

        if checks == 0:
            return 1.0, {"message": "No ordering patterns to check", "violations": 0}

        score = max(0.0, 1.0 - violations / checks)
        return score, {
            "ordering_checks": checks,
            "violations": violations,
            "write_before_read": first_write is not None and first_read is not None and first_write < first_read,
        }

    def _evaluate_backtracking(self, tool_spans: list[Span]) -> tuple[float, dict]:
        """Detect undo/redo patterns in the trajectory."""
        opposing_pairs = {
            "create": "delete", "add": "remove", "insert": "delete",
            "enable": "disable", "open": "close", "start": "stop",
            "set": "unset", "write": "revert",
        }

        tool_names = []
        for span in tool_spans:
            name = (span.tool_call.name if span.tool_call else span.name).lower()
            name = name.replace("_", " ").replace("-", " ")
            tool_names.append(name)

        backtracks = 0
        for i, name_i in enumerate(tool_names):
            for action, opposite in opposing_pairs.items():
                if action in name_i:
                    for j in range(i + 1, min(i + 5, len(tool_names))):
                        if opposite in tool_names[j]:
                            backtracks += 1
                            break

        score = max(0.0, 1.0 - backtracks * 0.3)
        return score, {
            "backtrack_count": backtracks,
            "trajectory_length": len(tool_names),
        }

    def _get_result_text(self, span: Span) -> str:
        if span.tool_call and span.tool_call.result is not None:
            return str(span.tool_call.result).lower()
        if span.output is not None:
            return str(span.output).lower()
        return ""

    def _extract_significant_tokens(self, text: str) -> set[str]:
        words = text.split()
        stop = {
            "the", "a", "an", "is", "to", "and", "or", "of", "in", "for",
            "with", "true", "false", "none", "null", "ok", "success",
        }
        return {w for w in words if len(w) > 3 and w not in stop}

    def _walk(self, spans: list[Span]) -> list[Span]:
        result: list[Span] = []
        for s in spans:
            result.append(s)
            result.extend(self._walk(s.children))
        return result

    def _build_reason(
        self,
        redundancy: float,
        utilization: float,
        ordering: float,
        backtracking: float,
        redundancy_details: dict,
        backtrack_details: dict,
    ) -> str:
        parts: list[str] = []

        if redundancy < 0.7:
            dups = redundancy_details.get("duplicate_calls", 0)
            parts.append(f"Redundancy detected: {dups} duplicate call(s)")
        if utilization < 0.5:
            parts.append("Many tool results unused in final output")
        if ordering < 1.0:
            parts.append("Suboptimal ordering detected (e.g., write before read)")
        if backtracking < 1.0:
            bt = backtrack_details.get("backtrack_count", 0)
            parts.append(f"Backtracking detected: {bt} undo/redo pair(s)")

        if not parts:
            parts.append("Trajectory is well-optimized")

        avg = (redundancy + utilization + ordering + backtracking) / 4
        if avg >= 0.8:
            parts.insert(0, "Highly optimal trajectory")
        elif avg >= 0.5:
            parts.insert(0, "Moderately optimal trajectory")
        else:
            parts.insert(0, "Suboptimal trajectory")

        return ". ".join(parts)


def _stable_repr(val: Any) -> str:
    """Create a stable string representation for deduplication."""
    if isinstance(val, dict):
        return str(sorted(val.items()))
    return str(val)
