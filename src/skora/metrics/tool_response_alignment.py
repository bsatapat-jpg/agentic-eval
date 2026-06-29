"""Tool-Response Alignment metric -- are MCP/RAG tool calls and their
responses actually relevant to the user's query?

This metric validates the semantic pipeline:
  user query → tool arguments → tool response

It catches agents that call the right tool with wrong arguments,
or whose tool responses are irrelevant to the task at hand.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import MetricResult, SkillSpec, Span, SpanType, Trace
from .base import BaseMetric


class ToolResponseAlignmentMetric(BaseMetric):
    """Measures whether tool calls and their responses are aligned with the user query.

    For each tool call in the trajectory, evaluates three sub-scores:

    1. **Argument Relevance**: Do the tool arguments relate to the user query?
       Catches agents that call the right tool with nonsensical arguments.

    2. **Response Relevance**: Does the tool response contain information
       related to the query? Catches MCP/RAG calls that return irrelevant data.

    3. **Call Necessity**: Did the agent actually use the tool response
       downstream (in later spans or the final output)? Catches wasted calls.

    Works with heuristic keyword analysis by default. Enable LLM judge
    for deep semantic evaluation.
    """

    name = "tool_response_alignment"
    description = "Are tool/MCP/RAG calls and responses relevant to the query?"
    tier = 2

    def __init__(self, use_llm_judge: bool = False) -> None:
        self.use_llm_judge = use_llm_judge

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        tool_spans = self._get_tool_spans(trajectory)

        if not tool_spans:
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="No tool calls in trajectory -- nothing to evaluate",
                details={"tool_call_count": 0},
            )

        query_text = str(trajectory.input or "")
        if not query_text.strip():
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="No user query to compare against",
                details={"tool_call_count": len(tool_spans)},
            )

        if self.use_llm_judge and skill_spec:
            return self._score_with_llm(trajectory, tool_spans, skill_spec)

        return self._score_heuristic(trajectory, tool_spans, query_text)

    def _score_heuristic(
        self,
        trajectory: Trace,
        tool_spans: list[Span],
        query_text: str,
    ) -> MetricResult:
        query_tokens = self._extract_tokens(query_text)
        final_output_text = str(trajectory.output or "")
        final_tokens = self._extract_tokens(final_output_text)

        per_tool: list[dict[str, Any]] = []
        arg_scores: list[float] = []
        resp_scores: list[float] = []
        util_scores: list[float] = []

        for span in tool_spans:
            tool_name = span.tool_call.name if span.tool_call else span.name
            arg_text = self._flatten_value(
                span.tool_call.arguments if span.tool_call else span.input
            )
            resp_text = self._flatten_value(
                span.tool_call.result if span.tool_call else span.output
            )

            arg_relevance = self._token_overlap(query_tokens, self._extract_tokens(arg_text))
            resp_relevance = self._token_overlap(query_tokens, self._extract_tokens(resp_text))

            resp_tokens = self._extract_tokens(resp_text)
            utilization = self._token_overlap(resp_tokens, final_tokens) if resp_tokens else 0.0

            if span.tool_call and span.tool_call.error:
                resp_relevance = 0.0

            arg_scores.append(arg_relevance)
            resp_scores.append(resp_relevance)
            util_scores.append(utilization)

            per_tool.append({
                "tool": tool_name,
                "argument_relevance": round(arg_relevance, 3),
                "response_relevance": round(resp_relevance, 3),
                "response_utilization": round(utilization, 3),
                "has_error": bool(span.tool_call and span.tool_call.error),
            })

        avg_arg = sum(arg_scores) / len(arg_scores)
        avg_resp = sum(resp_scores) / len(resp_scores)
        avg_util = sum(util_scores) / len(util_scores)

        overall = avg_arg * 0.35 + avg_resp * 0.40 + avg_util * 0.25

        return MetricResult(
            metric_name=self.name,
            score=round(overall, 4),
            passed=overall >= 0.3,
            reason=self._build_reason(avg_arg, avg_resp, avg_util, per_tool),
            details={
                "tool_call_count": len(tool_spans),
                "avg_argument_relevance": round(avg_arg, 3),
                "avg_response_relevance": round(avg_resp, 3),
                "avg_response_utilization": round(avg_util, 3),
                "per_tool": per_tool,
            },
        )

    def _score_with_llm(
        self,
        trajectory: Trace,
        tool_spans: list[Span],
        skill_spec: SkillSpec,
    ) -> MetricResult:
        try:
            from ..judges.llm_judge import LLMJudge

            judge = LLMJudge()
            tool_summaries = []
            for span in tool_spans[:10]:
                tc = span.tool_call
                if tc:
                    tool_summaries.append(
                        f"- {tc.name}(args={str(tc.arguments)[:200]}) → "
                        f"{str(tc.result)[:200]}"
                    )

            prompt = (
                f"Evaluate whether each tool call is relevant to the user query "
                f"and whether its response is useful.\n\n"
                f"USER QUERY: {trajectory.input}\n\n"
                f"SKILL: {skill_spec.name}: {skill_spec.description}\n\n"
                f"TOOL CALLS:\n" + "\n".join(tool_summaries) + "\n\n"
                f"FINAL OUTPUT: {str(trajectory.output)[:500]}\n\n"
                f"Score 0.0 (irrelevant calls) to 1.0 (perfectly aligned)."
            )
            result = judge.evaluate(prompt)
            return MetricResult(
                metric_name=self.name,
                score=result.score,
                passed=result.score >= 0.3,
                reason=result.reason,
                details={"judge_model": result.model},
            )
        except ImportError:
            query_text = str(trajectory.input or "")
            return self._score_heuristic(trajectory, tool_spans, query_text)

    def _get_tool_spans(self, trajectory: Trace) -> list[Span]:
        result: list[Span] = []
        for span in self._walk(trajectory.spans):
            if span.tool_call or span.type in (SpanType.TOOL_CALL, SpanType.RETRIEVAL):
                result.append(span)
        return result

    def _walk(self, spans: list[Span]) -> list[Span]:
        result: list[Span] = []
        for s in spans:
            result.append(s)
            result.extend(self._walk(s.children))
        return result

    def _extract_tokens(self, text: str) -> set[str]:
        if not text:
            return set()
        words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        stop = {
            "the", "a", "an", "is", "to", "and", "or", "of", "in", "for",
            "with", "on", "at", "by", "from", "this", "that", "it", "be",
            "as", "are", "was", "were", "been", "has", "have", "had", "do",
            "does", "did", "not", "no", "but", "if", "so", "up", "out",
            "true", "false", "none", "null", "undefined",
        }
        return {w for w in words if len(w) > 2 and w not in stop}

    def _token_overlap(self, tokens_a: set[str], tokens_b: set[str]) -> float:
        if not tokens_a or not tokens_b:
            return 0.0
        overlap = tokens_a & tokens_b
        return len(overlap) / max(len(tokens_a), 1)

    def _flatten_value(self, val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            return " ".join(str(v) for v in val.values())
        if isinstance(val, (list, tuple)):
            return " ".join(str(v) for v in val)
        return str(val)

    def _build_reason(
        self,
        avg_arg: float,
        avg_resp: float,
        avg_util: float,
        per_tool: list[dict],
    ) -> str:
        parts: list[str] = []
        parts.append(f"Argument relevance: {avg_arg:.0%}")
        parts.append(f"Response relevance: {avg_resp:.0%}")
        parts.append(f"Response utilization: {avg_util:.0%}")

        errored = [t for t in per_tool if t.get("has_error")]
        if errored:
            parts.append(f"{len(errored)} tool call(s) returned errors")

        low_relevance = [t for t in per_tool if t["response_relevance"] < 0.2]
        if low_relevance:
            names = [t["tool"] for t in low_relevance[:3]]
            parts.append(f"Low-relevance responses from: {', '.join(names)}")

        return ". ".join(parts)
