"""Core data models for agentic-eval."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SpanType(str, Enum):
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    RETRIEVAL = "retrieval"
    AGENT_STEP = "agent_step"
    ERROR = "error"
    CUSTOM = "custom"


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class ComparisonVerdict(str, Enum):
    A_BETTER = "a_better"
    B_BETTER = "b_better"
    NO_DIFFERENCE = "no_difference"


# --- Trajectory Models ---


class ToolCall(BaseModel):
    """A single tool/function call within a trajectory."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: str | None = None
    duration_ms: float | None = None


class Span(BaseModel):
    """A single span within a trace -- one logical unit of work."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: SpanType = SpanType.CUSTOM
    name: str = ""
    input: Any = None
    output: Any = None
    error: str | None = None
    tool_call: ToolCall | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    children: list[Span] = Field(default_factory=list)


class Trace(BaseModel):
    """A complete execution trace from an agent run."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    input: Any = None
    output: Any = None
    spans: list[Span] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def tool_calls(self) -> list[ToolCall]:
        """Extract all tool calls from the trace."""
        calls: list[ToolCall] = []
        for span in self._walk_spans(self.spans):
            if span.tool_call:
                calls.append(span.tool_call)
        return calls

    @property
    def errors(self) -> list[Span]:
        """Extract all error spans."""
        return [s for s in self._walk_spans(self.spans) if s.error]

    @property
    def duration_ms(self) -> float | None:
        if self.started_at and self.ended_at:
            return max(0.0, (self.ended_at - self.started_at).total_seconds() * 1000)
        return None

    def print_tree(self) -> None:
        """Pretty-print the trace as a tree using Rich."""
        from rich.console import Console
        from rich.tree import Tree

        console = Console()
        duration = f" ({self.duration_ms:.0f}ms)" if self.duration_ms else ""
        tree = Tree(
            f"[bold]Trace[/bold] {self.id[:8]}{duration}  "
            f"in=[dim]{str(self.input)[:50]}[/dim]  "
            f"out=[dim]{str(self.output)[:50]}[/dim]"
        )
        for span in self.spans:
            self._add_span_to_tree(tree, span)
        console.print(tree)

    def _add_span_to_tree(self, parent, span: Span) -> None:
        type_colors = {
            "tool_call": "blue",
            "llm_call": "magenta",
            "error": "red",
            "agent_step": "cyan",
        }
        color = type_colors.get(span.type.value, "white")
        error_str = f" [red]ERR: {span.error[:40]}[/red]" if span.error else ""
        dur = ""
        if span.started_at and span.ended_at:
            ms = (span.ended_at - span.started_at).total_seconds() * 1000
            dur = f" ({ms:.0f}ms)"

        label = f"[{color}]{span.type.value}[/{color}] {span.name}{dur}{error_str}"
        node = parent.add(label)
        for child in span.children:
            self._add_span_to_tree(node, child)

    def _walk_spans(self, spans: list[Span]) -> list[Span]:
        result: list[Span] = []
        for span in spans:
            result.append(span)
            result.extend(self._walk_spans(span.children))
        return result


# --- Skill Specification Models ---


class SkillStep(BaseModel):
    """A single step defined in a SKILL.md workflow."""

    order: int
    description: str
    expected_tools: list[str] = Field(default_factory=list)
    required: bool = True


class SkillSpec(BaseModel):
    """Parsed representation of a SKILL.md file."""

    name: str = ""
    description: str = ""
    trigger_conditions: list[str] = Field(default_factory=list)
    steps: list[SkillStep] = Field(default_factory=list)
    expected_tools: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    raw_content: str = ""
    file_path: str | None = None
    version_hash: str = ""

    @classmethod
    def compute_hash(cls, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# --- Evaluation Result Models ---


class MetricResult(BaseModel):
    """Result from a single metric evaluation."""

    metric_name: str
    score: float = Field(ge=0.0, le=1.0)
    passed: bool = True
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    threshold: float | None = None


class EvalResult(BaseModel):
    """Complete evaluation result for one run."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_name: str = ""
    skill_path: str | None = None
    skill_version_hash: str = ""
    verdict: Verdict = Verdict.PASS
    overall_score: float = 0.0
    metric_results: list[MetricResult] = Field(default_factory=list)
    trace: Trace | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "skill": self.skill_name,
            "verdict": self.verdict.value,
            "overall_score": self.overall_score,
            "metrics": {m.metric_name: m.score for m in self.metric_results},
            "timestamp": self.timestamp.isoformat(),
        }

    def print(self, verbose: bool = False) -> None:
        """Pretty-print the evaluation result to console using Rich."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.tree import Tree

        console = Console()

        verdict_styles = {"pass": "bold green", "fail": "bold red", "partial": "bold yellow"}
        v_style = verdict_styles.get(self.verdict.value, "white")
        grade = self.metadata.get("grade", "")
        grade_str = f"  Grade: {grade}" if grade else ""

        console.print(Panel(
            f"[bold]Skill:[/bold] {self.skill_name or 'N/A'}\n"
            f"[bold]Verdict:[/bold] [{v_style}]{self.verdict.value.upper()}[/{v_style}]{grade_str}\n"
            f"[bold]Score:[/bold] {self.overall_score:.1%}\n"
            f"[bold]Version:[/bold] {self.skill_version_hash[:8] or 'N/A'}",
            title=f"Evaluation Result [{self.id[:8]}]",
            border_style="green" if self.verdict == Verdict.PASS else "red",
        ))

        if self.metric_results:
            table = Table(title="Metric Breakdown", show_lines=True)
            table.add_column("Metric", style="cyan", min_width=20)
            table.add_column("Score", justify="right", min_width=8)
            table.add_column("Status", justify="center", min_width=6)
            table.add_column("Reason", max_width=60)

            for mr in self.metric_results:
                score_str = f"{mr.score:.1%}"
                status = "[green]PASS[/green]" if mr.passed else "[red]FAIL[/red]"
                table.add_row(mr.metric_name, score_str, status, mr.reason[:60])

            console.print(table)

        if verbose and self.trace:
            self.trace.print_tree()

    def __repr__(self) -> str:
        return (
            f"EvalResult(skill={self.skill_name!r}, verdict={self.verdict.value!r}, "
            f"score={self.overall_score:.3f}, metrics={len(self.metric_results)})"
        )


# --- Security Models ---


class SecurityFinding(BaseModel):
    """A single security finding from scanning a skill."""

    severity: Severity
    category: str
    description: str
    location: str = ""
    line_number: int | None = None
    recommendation: str = ""


class SecurityReport(BaseModel):
    """Complete security scan report."""

    skill_path: str
    skill_name: str = ""
    findings: list[SecurityFinding] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0, default=1.0)
    grade: str = "A"
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)


# --- Comparison Models ---


class ComparisonMetricResult(BaseModel):
    """Per-metric comparison between two skill versions."""

    metric_name: str
    score_a: float
    score_b: float
    delta: float = 0.0
    winner: str = ""


class ComparisonResult(BaseModel):
    """Result of comparing two skill versions."""

    skill_a_path: str
    skill_b_path: str
    skill_a_hash: str = ""
    skill_b_hash: str = ""
    verdict: ComparisonVerdict = ComparisonVerdict.NO_DIFFERENCE
    lift: float = 0.0
    per_metric: list[ComparisonMetricResult] = Field(default_factory=list)
    trials: int = 0
    eval_results_a: list[EvalResult] = Field(default_factory=list)
    eval_results_b: list[EvalResult] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
