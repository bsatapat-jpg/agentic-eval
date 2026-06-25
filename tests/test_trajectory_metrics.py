"""Tests for the trajectory-aware evaluation metrics.

These metrics evaluate the semantic pipeline:
  user query → tool selection → tool arguments → tool response → final output
"""

from datetime import datetime, timezone

import pytest

from agentic_eval.models import (
    MetricResult,
    SkillSpec,
    SkillStep,
    Span,
    SpanType,
    ToolCall,
    Trace,
)


def _now():
    return datetime.now(timezone.utc)


def _tool_span(name, args=None, result=None, error=None):
    """Helper to build a tool call span."""
    tc = ToolCall(
        name=name,
        arguments=args or {},
        result=result,
        error=error,
    )
    return Span(
        name=f"tool:{name}",
        type=SpanType.TOOL_CALL,
        input=args,
        output=result,
        tool_call=tc,
        started_at=_now(),
        ended_at=_now(),
    )


def _llm_span(model="gpt-4", output=None):
    return Span(
        name=f"llm:{model}",
        type=SpanType.LLM_CALL,
        output=output,
        started_at=_now(),
        ended_at=_now(),
    )


# ═══════════════════════════════════════════════════════
# ToolResponseAlignmentMetric
# ═══════════════════════════════════════════════════════

class TestToolResponseAlignment:

    def _metric(self):
        from agentic_eval.metrics.tool_response_alignment import ToolResponseAlignmentMetric
        return ToolResponseAlignmentMetric()

    def test_perfectly_aligned_tool_call(self):
        """Tool args and response directly match the query."""
        trace = Trace(
            input="What is the weather in Paris?",
            output="The weather in Paris is sunny, 25°C.",
            spans=[
                _tool_span(
                    "get_weather",
                    args={"city": "Paris"},
                    result={"condition": "sunny", "temp": "25°C", "city": "Paris"},
                ),
            ],
        )
        result = self._metric().score(trace)
        assert result.score >= 0.5, f"Expected high alignment, got {result.score}"
        assert result.passed

    def test_irrelevant_tool_call(self):
        """Tool call has nothing to do with the query."""
        trace = Trace(
            input="What is the weather in Paris?",
            output="I don't know the weather.",
            spans=[
                _tool_span(
                    "calculate_tax",
                    args={"income": 50000, "state": "CA"},
                    result={"tax": 12500},
                ),
            ],
        )
        result = self._metric().score(trace)
        assert result.score < 0.5, f"Expected low alignment, got {result.score}"

    def test_no_tool_calls(self):
        """No tool calls at all -- metric is N/A."""
        trace = Trace(input="Hello", output="Hi there")
        result = self._metric().score(trace)
        assert result.score == 1.0

    def test_tool_error_penalized(self):
        """Tool calls that error should lower the response relevance."""
        trace = Trace(
            input="Search for python documentation",
            output="Could not find documentation.",
            spans=[
                _tool_span(
                    "web_search",
                    args={"query": "python documentation"},
                    result=None,
                    error="ConnectionTimeout",
                ),
            ],
        )
        result = self._metric().score(trace)
        assert result.details["per_tool"][0]["has_error"]

    def test_multiple_tools_mixed_relevance(self):
        """Mix of relevant and irrelevant tool calls."""
        trace = Trace(
            input="Find the price of AAPL stock",
            output="AAPL is trading at $150.",
            spans=[
                _tool_span(
                    "get_stock_price",
                    args={"symbol": "AAPL"},
                    result={"price": 150, "symbol": "AAPL"},
                ),
                _tool_span(
                    "send_email",
                    args={"to": "admin@example.com", "body": "test"},
                    result={"status": "sent"},
                ),
            ],
        )
        result = self._metric().score(trace)
        per_tool = result.details["per_tool"]
        assert len(per_tool) == 2
        assert per_tool[0]["argument_relevance"] > per_tool[1]["argument_relevance"]

    def test_no_query_input(self):
        """No user input -- nothing to compare against."""
        trace = Trace(
            input=None,
            output="result",
            spans=[_tool_span("search", args={"q": "test"}, result="found")],
        )
        result = self._metric().score(trace)
        assert result.score == 1.0


# ═══════════════════════════════════════════════════════
# GroundednessMetric
# ═══════════════════════════════════════════════════════

class TestGroundedness:

    def _metric(self):
        from agentic_eval.metrics.grounding import GroundednessMetric
        return GroundednessMetric()

    def test_fully_grounded_output(self):
        """Output directly from tool response."""
        trace = Trace(
            input="What is the capital of France?",
            output="The capital of France is Paris.",
            spans=[
                _tool_span(
                    "lookup",
                    args={"query": "capital of France"},
                    result="The capital of France is Paris, a city of 2.1 million people.",
                ),
            ],
        )
        result = self._metric().score(trace)
        assert result.score > 0.5
        assert result.passed

    def test_ungrounded_fabricated_output(self):
        """Output contains information not in any tool response."""
        trace = Trace(
            input="What is project Alpha?",
            output="Project Alpha launched on 2024-03-15 and generated $5M revenue with 10,000 users.",
            spans=[
                _tool_span(
                    "search_docs",
                    args={"query": "project Alpha"},
                    result="Project Alpha is an internal tool for data processing.",
                ),
            ],
        )
        result = self._metric().score(trace)
        details = result.details
        assert len(details.get("ungrounded_entities", [])) > 0 or result.score < 0.9

    def test_no_tool_responses(self):
        """Pure LLM generation with no tools -- groundedness is N/A."""
        trace = Trace(input="Hello", output="Hi there!")
        result = self._metric().score(trace)
        assert result.score == 1.0

    def test_no_output(self):
        """No output at all."""
        trace = Trace(
            input="test",
            output=None,
            spans=[_tool_span("search", result="some data")],
        )
        result = self._metric().score(trace)
        assert result.score == 0.0

    def test_multiple_evidence_sources(self):
        """Output grounded across multiple tool responses."""
        trace = Trace(
            input="Compare Python and Rust performance",
            output="Python is interpreted and slower. Rust is compiled and faster with memory safety.",
            spans=[
                _tool_span("search", args={"q": "Python performance"},
                           result="Python is an interpreted language, generally slower than compiled languages."),
                _tool_span("search", args={"q": "Rust performance"},
                           result="Rust is a compiled language known for speed and memory safety."),
            ],
        )
        result = self._metric().score(trace)
        assert result.score > 0.4


# ═══════════════════════════════════════════════════════
# TrajectoryOptimalityMetric
# ═══════════════════════════════════════════════════════

class TestTrajectoryOptimality:

    def _metric(self):
        from agentic_eval.metrics.trajectory_optimality import TrajectoryOptimalityMetric
        return TrajectoryOptimalityMetric()

    def test_optimal_trajectory(self):
        """Clean, non-redundant, logically ordered trajectory."""
        trace = Trace(
            input="Read the config and update the setting",
            output="Setting updated successfully",
            spans=[
                _tool_span("read_config", result={"setting": "old_value"}),
                _tool_span("update_config", args={"setting": "new_value"}, result="ok"),
            ],
        )
        result = self._metric().score(trace)
        assert result.score >= 0.7
        assert result.passed

    def test_redundant_calls(self):
        """Same tool called multiple times with same args."""
        trace = Trace(
            input="Search for documentation",
            output="Found docs.",
            spans=[
                _tool_span("web_search", args={"q": "docs"}, result="result1"),
                _tool_span("web_search", args={"q": "docs"}, result="result1"),
                _tool_span("web_search", args={"q": "docs"}, result="result1"),
            ],
        )
        result = self._metric().score(trace)
        assert result.details["redundancy"]["duplicate_calls"] == 2
        assert result.details["scores"]["redundancy"] < 1.0

    def test_write_before_read_ordering(self):
        """Writing before reading is a logical ordering violation."""
        trace = Trace(
            input="Read data and process it",
            output="Done",
            spans=[
                _tool_span("write_output", args={"data": "premature"}, result="ok"),
                _tool_span("read_input", result={"data": "actual_input"}),
            ],
        )
        result = self._metric().score(trace)
        ordering = result.details["logical_ordering"]
        assert ordering.get("write_before_read", False)

    def test_backtracking_detected(self):
        """Create followed by delete is backtracking."""
        trace = Trace(
            input="Set up environment",
            output="Done",
            spans=[
                _tool_span("create_file", args={"name": "test.txt"}, result="created"),
                _tool_span("delete_file", args={"name": "test.txt"}, result="deleted"),
                _tool_span("create_file", args={"name": "test.txt"}, result="created"),
            ],
        )
        result = self._metric().score(trace)
        assert result.details["backtracking"]["backtrack_count"] > 0

    def test_single_tool_call_passes(self):
        """Too few calls to evaluate optimality."""
        trace = Trace(
            input="Search",
            output="Found it",
            spans=[_tool_span("search", result="found")],
        )
        result = self._metric().score(trace)
        assert result.score == 1.0

    def test_unused_results_detected(self):
        """Tool results not appearing in output or later calls."""
        trace = Trace(
            input="Get weather",
            output="I cannot help with that.",
            spans=[
                _tool_span("get_weather", args={"city": "NYC"},
                           result="Sunny, 75F in New York City today"),
                _tool_span("get_news", args={"topic": "sports"},
                           result="Lakers won the championship game last night"),
            ],
        )
        result = self._metric().score(trace)
        util = result.details["result_utilization"]
        assert util["results_utilized"] < util["total_with_results"]


# ═══════════════════════════════════════════════════════
# HallucinationMetric
# ═══════════════════════════════════════════════════════

class TestHallucination:

    def _metric(self):
        from agentic_eval.metrics.hallucination import HallucinationMetric
        return HallucinationMetric()

    def test_no_hallucination(self):
        """All facts in output come from tool responses."""
        trace = Trace(
            input="What is the server status?",
            output="Server uptime is 99.9% as of 2024-01-15.",
            spans=[
                _tool_span(
                    "check_status",
                    result="Server uptime: 99.9%. Last checked: 2024-01-15.",
                ),
            ],
        )
        result = self._metric().score(trace)
        assert result.score >= 0.7
        assert result.details["unverified"] == 0

    def test_hallucinated_numbers(self):
        """Output contains numbers not present in any evidence."""
        trace = Trace(
            input="How many users do we have?",
            output="We have 50,000 active users and $2.5M revenue this quarter.",
            spans=[
                _tool_span(
                    "get_user_count",
                    result="Current active users: 12,500",
                ),
            ],
        )
        result = self._metric().score(trace)
        assert result.details["unverified"] > 0

    def test_hallucinated_url(self):
        """Output contains a URL not in any evidence source."""
        trace = Trace(
            input="Where is the documentation?",
            output="Documentation is at https://docs.example.com/v2/guide",
            spans=[
                _tool_span(
                    "search_docs",
                    result="The project documentation is maintained internally.",
                ),
            ],
        )
        result = self._metric().score(trace)
        unverified = result.details.get("unverified_facts", [])
        assert any("https://" in f for f in unverified)

    def test_no_output(self):
        """No output -- nothing to hallucinate."""
        trace = Trace(input="test", output="")
        result = self._metric().score(trace)
        assert result.score == 1.0

    def test_no_evidence(self):
        """Pure generation with no tools -- can't verify, so N/A."""
        trace = Trace(input="test", output="The answer is 42.")
        result = self._metric().score(trace)
        assert result.score == 1.0

    def test_facts_from_user_query_not_hallucinated(self):
        """Facts present in the user's original query shouldn't be flagged."""
        trace = Trace(
            input="The project launched on 2024-06-01 with version v2.1.0",
            output="As you mentioned, the project launched on 2024-06-01 with version v2.1.0.",
            spans=[
                _tool_span("confirm", result="confirmed"),
            ],
        )
        result = self._metric().score(trace)
        assert result.score >= 0.7

    def test_file_path_hallucination(self):
        """Output references a file path not in evidence."""
        trace = Trace(
            input="Where is the config?",
            output="The config file is at /etc/myapp/config.yaml",
            spans=[
                _tool_span(
                    "find_file",
                    args={"name": "config"},
                    result="Config found at /opt/app/settings.json",
                ),
            ],
        )
        result = self._metric().score(trace)
        unverified = result.details.get("unverified_facts", [])
        has_wrong_path = any("/etc/myapp/config.yaml" in f for f in unverified)
        assert has_wrong_path or result.score < 1.0


# ═══════════════════════════════════════════════════════
# Integration: all 11 metrics run together
# ═══════════════════════════════════════════════════════

class TestFullEvaluatorWithTrajectoryMetrics:
    """Ensure the SkillAdherenceEvaluator runs all 11 metrics including
    the new trajectory-aware ones."""

    def test_evaluator_runs_all_11_metrics(self):
        from agentic_eval.evaluators.skill_adherence import SkillAdherenceEvaluator

        spec = SkillSpec(
            name="test-skill",
            expected_tools=["search", "format_output"],
            steps=[
                SkillStep(order=1, description="Search for data", expected_tools=["search"]),
                SkillStep(order=2, description="Format the output", expected_tools=["format_output"]),
            ],
        )

        trace = Trace(
            input="Find product pricing",
            output="Product A costs $99. Product B costs $149.",
            spans=[
                _tool_span("search", args={"query": "product pricing"},
                           result="Product A: $99, Product B: $149"),
                _tool_span("format_output", args={"data": "pricing"},
                           result="formatted table"),
            ],
        )

        evaluator = SkillAdherenceEvaluator(skill=spec)
        result = evaluator.evaluate(trace)

        metric_names = {mr.metric_name for mr in result.metric_results}
        assert "tool_response_alignment" in metric_names
        assert "groundedness" in metric_names
        assert "trajectory_optimality" in metric_names
        assert "hallucination" in metric_names
        assert len(result.metric_results) == 11

    def test_registry_has_11_metrics(self):
        from agentic_eval.metrics import get_registry

        registry = get_registry()
        names = registry.names()
        assert len(names) == 11
        assert "tool_response_alignment" in names
        assert "groundedness" in names
        assert "trajectory_optimality" in names
        assert "hallucination" in names

    def test_api_list_metrics_returns_11(self):
        from agentic_eval.api import list_metrics

        metrics = list_metrics()
        assert len(metrics) == 11
        names = {m["name"] for m in metrics}
        assert "tool_response_alignment" in names
        assert "groundedness" in names

    def test_run_evaluation_with_new_metrics(self):
        from agentic_eval.api import run_evaluation

        trace = Trace(
            input="What is the status of project X?",
            output="Project X is on track with 85% completion.",
            spans=[
                _tool_span("get_project_status",
                           args={"project": "X"},
                           result="Project X: 85% complete, on track."),
            ],
        )
        result = run_evaluation(trace)
        assert result.overall_score > 0.0
        assert len(result.metric_results) == 11

    def test_filter_to_only_trajectory_metrics(self):
        from agentic_eval.api import run_evaluation

        trace = Trace(
            input="test",
            output="result",
            spans=[_tool_span("search", result="data")],
        )
        result = run_evaluation(
            trace,
            metrics=["groundedness", "hallucination", "tool_response_alignment"],
        )
        names = {mr.metric_name for mr in result.metric_results}
        assert names == {"groundedness", "hallucination", "tool_response_alignment"}
