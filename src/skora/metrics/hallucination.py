"""Hallucination Detection metric -- does the agent fabricate information
not present in any tool/MCP/RAG response or the original query?

This is complementary to the Groundedness metric but takes a different
approach: instead of measuring token overlap, it specifically looks for
*factual claims* (numbers, dates, names, URLs, code identifiers) in the
output that cannot be traced to any evidence source.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import MetricResult, SkillSpec, Span, SpanType, Trace
from .base import BaseMetric


class HallucinationMetric(BaseMetric):
    """Detects fabricated factual claims in the agent's output.

    Unlike the broader Groundedness metric, this focuses specifically on
    *verifiable facts* -- numbers, dates, names, URLs, file paths, code
    identifiers -- and checks whether each one can be traced back to:

    - The user's original query
    - A tool/MCP/RAG response
    - The skill specification

    Any verifiable fact in the output that appears in none of these
    sources is flagged as a potential hallucination.

    This metric is critical for MCP/RAG pipelines where agents must
    synthesize accurate information from retrieved documents.
    """

    name = "hallucination"
    description = "Does the output contain fabricated facts not from any evidence source?"
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
                score=1.0,
                passed=True,
                reason="No output to check for hallucinations",
            )

        evidence_corpus = self._build_evidence_corpus(trajectory, skill_spec)
        if not evidence_corpus.strip():
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="No evidence sources to verify against (pure generation)",
                details={"evidence_sources": 0},
            )

        if self.use_llm_judge and skill_spec:
            return self._score_with_llm(trajectory, evidence_corpus, skill_spec)

        return self._score_heuristic(output_text, evidence_corpus)

    def _score_heuristic(self, output_text: str, evidence: str) -> MetricResult:
        output_facts = self._extract_facts(output_text)
        evidence_facts = self._extract_facts(evidence)
        evidence_lower = evidence.lower()

        if not output_facts:
            return MetricResult(
                metric_name=self.name,
                score=1.0,
                passed=True,
                reason="No verifiable facts found in output",
                details={"output_facts": 0, "verified": 0, "unverified": 0},
            )

        verified: list[str] = []
        unverified: list[str] = []

        for fact in output_facts:
            if self._fact_in_evidence(fact, evidence_facts, evidence_lower):
                verified.append(fact)
            else:
                unverified.append(fact)

        total = len(output_facts)
        verification_rate = len(verified) / total if total > 0 else 1.0

        severity = self._assess_severity(unverified)
        penalty = severity * (1 - verification_rate)
        score = max(0.0, min(1.0, 1.0 - penalty))

        return MetricResult(
            metric_name=self.name,
            score=round(score, 4),
            passed=score >= 0.5,
            reason=self._build_reason(verified, unverified, score),
            details={
                "output_facts": total,
                "verified": len(verified),
                "unverified": len(unverified),
                "verification_rate": round(verification_rate, 3),
                "verified_facts": verified[:20],
                "unverified_facts": unverified[:20],
                "hallucination_severity": round(severity, 3),
            },
        )

    def _score_with_llm(
        self,
        trajectory: Trace,
        evidence: str,
        skill_spec: SkillSpec,
    ) -> MetricResult:
        try:
            from ..judges.llm_judge import LLMJudge

            judge = LLMJudge()
            prompt = (
                f"Check the agent's output for hallucinated facts.\n\n"
                f"USER QUERY: {trajectory.input}\n\n"
                f"EVIDENCE (from tool/RAG/MCP responses):\n{evidence[:3000]}\n\n"
                f"AGENT OUTPUT: {str(trajectory.output)[:2000]}\n\n"
                f"Identify any specific facts (numbers, dates, names, URLs, "
                f"code identifiers) in the output that are NOT supported by "
                f"the evidence or the user query.\n\n"
                f"Score 1.0 (no hallucinations) to 0.0 (completely fabricated)."
            )
            result = judge.evaluate(prompt)
            return MetricResult(
                metric_name=self.name,
                score=result.score,
                passed=result.score >= 0.5,
                reason=result.reason,
                details={"judge_model": result.model},
            )
        except ImportError:
            return self._score_heuristic(
                str(trajectory.output or ""), evidence
            )

    def _build_evidence_corpus(
        self, trajectory: Trace, skill_spec: SkillSpec | None
    ) -> str:
        parts: list[str] = []

        if trajectory.input:
            parts.append(str(trajectory.input))

        for span in self._walk(trajectory.spans):
            if span.type in (SpanType.TOOL_CALL, SpanType.RETRIEVAL):
                if span.tool_call and span.tool_call.result is not None:
                    parts.append(str(span.tool_call.result))
                if span.output is not None:
                    parts.append(str(span.output))
                if span.tool_call:
                    parts.append(str(span.tool_call.arguments))

        if skill_spec:
            parts.append(skill_spec.raw_content)

        return "\n".join(parts)

    def _extract_facts(self, text: str) -> list[str]:
        """Extract verifiable factual claims from text."""
        facts: list[str] = []

        facts.extend(re.findall(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", text))
        facts.extend(re.findall(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b", text, re.IGNORECASE))

        facts.extend(re.findall(r"\b\d+(?:\.\d+)?(?:\s*%|\s*percent)\b", text))
        facts.extend(re.findall(r"\$\d+(?:,\d{3})*(?:\.\d{2})?\b", text))
        facts.extend(re.findall(r"\b\d{4,}\b", text))

        facts.extend(re.findall(r"https?://[^\s\)\"'>]+", text))
        facts.extend(re.findall(r"[\w.-]+@[\w.-]+\.\w+", text))

        facts.extend(re.findall(r"(?:/[\w.-]+){2,}", text))
        facts.extend(re.findall(r"\b\w+\.(?:py|js|ts|java|go|rs|rb|cpp|c|h|md|yaml|yml|json|toml|xml|sql)\b", text))

        facts.extend(re.findall(r"v\d+\.\d+(?:\.\d+)?(?:-\w+)?", text))

        seen = set()
        unique_facts = []
        for f in facts:
            f_normalized = f.strip().lower()
            if f_normalized not in seen and len(f_normalized) > 1:
                seen.add(f_normalized)
                unique_facts.append(f.strip())
        return unique_facts

    def _fact_in_evidence(
        self, fact: str, evidence_facts: list[str], evidence_lower: str
    ) -> bool:
        fact_lower = fact.lower().strip()

        if fact_lower in evidence_lower:
            return True

        for ef in evidence_facts:
            if fact_lower == ef.lower().strip():
                return True

        core = re.sub(r"[^\d.]", "", fact_lower)
        if core and len(core) >= 3:
            if core in evidence_lower:
                return True

        return False

    def _assess_severity(self, unverified: list[str]) -> float:
        """Assess how severe the hallucinations are. Numbers and URLs
        are more serious than file paths."""
        if not unverified:
            return 0.0

        severity = 0.0
        for fact in unverified:
            if re.match(r"\$\d", fact) or re.match(r"\d+.*%", fact):
                severity += 1.5
            elif re.match(r"https?://", fact):
                severity += 1.2
            elif re.match(r"v\d+\.\d+", fact):
                severity += 1.0
            elif re.match(r"\d{4}[-/]", fact):
                severity += 1.0
            else:
                severity += 0.5

        return min(2.0, severity / max(len(unverified), 1))

    def _walk(self, spans: list[Span]) -> list[Span]:
        result: list[Span] = []
        for s in spans:
            result.append(s)
            result.extend(self._walk(s.children))
        return result

    def _build_reason(
        self,
        verified: list[str],
        unverified: list[str],
        score: float,
    ) -> str:
        total = len(verified) + len(unverified)
        parts: list[str] = []

        if not unverified:
            parts.append(f"All {total} verifiable facts traced to evidence sources")
        else:
            parts.append(
                f"{len(verified)}/{total} facts verified, "
                f"{len(unverified)} potentially hallucinated"
            )
            sample = unverified[:3]
            parts.append(f"Unverified: {', '.join(sample)}")

        if score >= 0.9:
            parts.insert(0, "No hallucinations detected")
        elif score >= 0.7:
            parts.insert(0, "Minor potential hallucinations")
        elif score >= 0.5:
            parts.insert(0, "Some unverified claims detected")
        else:
            parts.insert(0, "Significant hallucination risk")

        return ". ".join(parts)
