"""scora: Trajectory-based evaluation framework for AI agent skills.

Quick start:

    from scora import evaluate, run_evaluation, Trace

    # Decorator approach
    @evaluate(skill="./SKILL.md", auto_save=True)
    async def my_agent(query: str) -> str:
        ...

    # Functional approach
    result = run_evaluation(trace, skill="./SKILL.md")
    result.print()
"""

from .models import (
    ComparisonMetricResult,
    ComparisonResult,
    ComparisonVerdict,
    EvalResult,
    MetricResult,
    SecurityFinding,
    SecurityReport,
    Severity,
    SkillSpec,
    SkillStep,
    Span,
    SpanType,
    Trace,
    ToolCall,
    Verdict,
)
from .skill_parser import parse_skill
from .tracer import (
    async_span_context,
    async_trace_context,
    get_current_span,
    get_current_trace,
    record_error,
    record_llm_call,
    record_tool_call,
    span_context,
    trace_context,
)
from .decorators import evaluate, trace_skill
from .assertions import assert_skill, load_golden_cases, SkillAssertionError
from .store import ResultStore
from .api import (
    batch_evaluate,
    compare_skills,
    list_metrics,
    run_evaluation,
    scan_security,
)
from .metrics import get_registry, register_metric
from .metrics.base import BaseMetric
from .config import EvalConfig, load_config
from .agent_evaluator import AgentEvaluator

__version__ = "0.1.0"

__all__ = [
    # Models
    "ComparisonMetricResult",
    "ComparisonResult",
    "ComparisonVerdict",
    "EvalResult",
    "MetricResult",
    "SecurityFinding",
    "SecurityReport",
    "Severity",
    "SkillSpec",
    "SkillStep",
    "Span",
    "SpanType",
    "Trace",
    "ToolCall",
    "Verdict",
    # Parser
    "parse_skill",
    # Tracer (sync + async)
    "async_span_context",
    "async_trace_context",
    "get_current_span",
    "get_current_trace",
    "record_error",
    "record_llm_call",
    "record_tool_call",
    "span_context",
    "trace_context",
    # Decorators
    "evaluate",
    "trace_skill",
    # High-level API
    "batch_evaluate",
    "compare_skills",
    "list_metrics",
    "run_evaluation",
    "scan_security",
    # Assertions
    "assert_skill",
    "load_golden_cases",
    "SkillAssertionError",
    # Store
    "ResultStore",
    # Metrics extension
    "BaseMetric",
    "get_registry",
    "register_metric",
    # Config & agent evaluation
    "AgentEvaluator",
    "EvalConfig",
    "load_config",
]
