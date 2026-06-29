"""Groundedness metric -- is the agent's output faithful to the evidence
gathered from tool/MCP/RAG responses?

This is the anti-hallucination metric for tool-augmented agents.
An agent that produces claims not supported by any tool response
is considered "ungrounded."
"""

from __future__ import annotations

import re
from typing import Any

from ..models import MetricResult, SkillSpec, Span, SpanType, Trace
from .base import BaseMetric


class GroundednessMetric(BaseMetric):
    """Measures whether the final output is grounded in tool/RAG/MCP evidence.

    Evaluates three dimensions:

    1. **Claim Coverage**: What fraction of claims/entities in the output
       can be traced back to a tool response?

    2. **Evidence Utilization**: Of all the evidence gathered from tools,
       how much was actually used in the final output?

    3. **Unsupported Claims**: Are there statements in the output that
       appear in no tool response? (potential hallucinations)

    Particularly important for RAG pipelines where the agent must
    synthesize retrieved documents into a faithful answer.
    """

    name = "groundedness"
    description = "Is the output grounded in tool/RAG/MCP response evidence?"
    tier = 1

    def __init__(self, use_llm_judge: bool = False) -> None:
        self.use_llm_judge = use_llm_judge

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        output_text = str(trajectory.output or "")
        if not output_text.strip():
            return MetricResult(
                metric_name=self.name,
                score=0.0,
                passed=False,
                reason="No output to evaluate groundedness",
            )

        evidence_spans = self._collect_evidence(trajectory)
        if not evidence_spans:
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="No tool/RAG responses to ground against (pure LLM generation)",
                details={"evidence_sources": 0},
            )

        if self.use_llm_judge and skill_spec:
            return self._score_with_llm(trajectory, evidence_spans, skill_spec)

        return self._score_heuristic(output_text, evidence_spans, trajectory)

    def _score_heuristic(
        self,
        output_text: str,
        evidence_spans: list[Span],
        trajectory: Trace,
    ) -> MetricResult:
        evidence_corpus = self._build_evidence_corpus(evidence_spans)
        evidence_tokens = self._extract_tokens(evidence_corpus)
        input_tokens = self._extract_tokens(str(trajectory.input or ""))

        output_tokens = self._extract_tokens(output_text)
        output_entities = self._extract_entities(output_text)
        evidence_entities = self._extract_entities(evidence_corpus)

        grounded_tokens = output_tokens & (evidence_tokens | input_tokens)
        novel_tokens = output_tokens - evidence_tokens - input_tokens - self._common_words()
        claim_coverage = len(grounded_tokens) / max(len(output_tokens), 1)

        utilized_evidence = evidence_tokens & output_tokens
        evidence_utilization = len(utilized_evidence) / max(len(evidence_tokens), 1)

        grounded_entities = output_entities & evidence_entities
        entity_grounding = (
            len(grounded_entities) / max(len(output_entities), 1)
            if output_entities
            else 1.0
        )

        ungrounded_entities = output_entities - evidence_entities - self._extract_tokens(
            str(trajectory.input or "")
        )

        overall = (
            claim_coverage * 0.40
            + entity_grounding * 0.40
            + evidence_utilization * 0.20
        )

        return MetricResult(
            metric_name=self.name,
            score=round(min(1.0, overall), 4),
            passed=overall >= 0.4,
            reason=self._build_reason(claim_coverage, entity_grounding, evidence_utilization, ungrounded_entities),
            details={
                "evidence_sources": len(evidence_spans),
                "claim_coverage": round(claim_coverage, 3),
                "entity_grounding": round(entity_grounding, 3),
                "evidence_utilization": round(evidence_utilization, 3),
                "output_entities": sorted(output_entities)[:20],
                "grounded_entities": sorted(grounded_entities)[:20],
                "ungrounded_entities": sorted(ungrounded_entities)[:20],
                "novel_token_count": len(novel_tokens),
            },
        )

    def _score_with_llm(
        self,
        trajectory: Trace,
        evidence_spans: list[Span],
        skill_spec: SkillSpec,
    ) -> MetricResult:
        try:
            from ..judges.llm_judge import LLMJudge

            judge = LLMJudge()
            evidence_text = self._build_evidence_corpus(evidence_spans)[:3000]

            prompt = (
                f"Evaluate whether the agent's output is faithfully grounded "
                f"in the evidence from tool/RAG/MCP responses.\n\n"
                f"USER QUERY: {trajectory.input}\n\n"
                f"EVIDENCE FROM TOOLS:\n{evidence_text}\n\n"
                f"AGENT OUTPUT: {str(trajectory.output)[:2000]}\n\n"
                f"Check for:\n"
                f"1. Claims in output not supported by evidence (hallucination)\n"
                f"2. Numbers/facts that don't match the evidence\n"
                f"3. Reasonable synthesis vs fabrication\n\n"
                f"Score 0.0 (completely fabricated) to 1.0 (fully grounded)."
            )
            result = judge.evaluate(prompt)
            return MetricResult(
                metric_name=self.name,
                score=result.score,
                passed=result.score >= 0.4,
                reason=result.reason,
                details={"judge_model": result.model, "evidence_sources": len(evidence_spans)},
            )
        except ImportError:
            output_text = str(trajectory.output or "")
            return self._score_heuristic(output_text, evidence_spans, trajectory)

    def _collect_evidence(self, trajectory: Trace) -> list[Span]:
        result: list[Span] = []
        for span in self._walk(trajectory.spans):
            if span.type in (SpanType.TOOL_CALL, SpanType.RETRIEVAL):
                if span.output or (span.tool_call and span.tool_call.result):
                    result.append(span)
        return result

    def _build_evidence_corpus(self, spans: list[Span]) -> str:
        parts: list[str] = []
        for span in spans:
            resp = span.tool_call.result if span.tool_call else span.output
            if resp is not None:
                parts.append(self._flatten(resp))
        return " ".join(parts)

    def _extract_tokens(self, text: str) -> set[str]:
        if not text:
            return set()
        words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        return {w for w in words if len(w) > 2}

    def _extract_entities(self, text: str) -> set[str]:
        """Extract potential entities: capitalized words, numbers, quoted strings."""
        if not text:
            return set()
        entities: set[str] = set()
        entities.update(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text))
        entities.update(re.findall(r"\b\d+(?:\.\d+)?(?:%|px|ms|kb|mb|gb)?\b", text))
        entities.update(re.findall(r'"([^"]{3,50})"', text))
        entities.update(re.findall(r"'([^']{3,50})'", text))
        return {e.lower().strip() for e in entities if len(e.strip()) > 2}

    def _common_words(self) -> set[str]:
        return {
            "the", "and", "for", "that", "this", "with", "from", "are",
            "was", "were", "been", "have", "has", "had", "can", "could",
            "will", "would", "should", "may", "might", "shall", "not",
            "but", "also", "then", "than", "when", "where", "which",
            "how", "what", "who", "whom", "its", "their", "your", "our",
            "result", "output", "response", "data", "information",
        }

    def _walk(self, spans: list[Span]) -> list[Span]:
        result: list[Span] = []
        for s in spans:
            result.append(s)
            result.extend(self._walk(s.children))
        return result

    def _flatten(self, val: Any) -> str:
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
        claim_coverage: float,
        entity_grounding: float,
        evidence_util: float,
        ungrounded: set[str],
    ) -> str:
        parts: list[str] = []
        parts.append(f"Claim coverage: {claim_coverage:.0%}")
        parts.append(f"Entity grounding: {entity_grounding:.0%}")
        parts.append(f"Evidence utilization: {evidence_util:.0%}")

        if ungrounded:
            sample = sorted(ungrounded)[:5]
            parts.append(f"Potentially ungrounded: {', '.join(sample)}")

        if claim_coverage >= 0.8 and entity_grounding >= 0.8:
            parts.insert(0, "Output well-grounded in tool evidence")
        elif claim_coverage >= 0.5:
            parts.insert(0, "Partially grounded output")
        else:
            parts.insert(0, "Output may contain ungrounded claims")

        return ". ".join(parts)
