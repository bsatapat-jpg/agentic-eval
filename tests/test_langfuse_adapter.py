"""Tests for the Langfuse adapter."""

from datetime import datetime, timezone

import pytest

from skora.adapters import from_langfuse
from skora.models import SpanType, Trace


class TestLangfuseObservationList:
    """Tests for the v2 observation-list input path."""

    def test_basic_observation_list(self):
        observations = [
            {
                "id": "obs-root",
                "traceId": "trace-1",
                "type": "SPAN",
                "name": "agent_run",
                "input": {"query": "What is the status?"},
                "output": "Project is on track",
                "startTime": "2024-06-15T10:00:00Z",
                "endTime": "2024-06-15T10:00:05Z",
            },
            {
                "id": "obs-tool",
                "traceId": "trace-1",
                "parentObservationId": "obs-root",
                "type": "SPAN",
                "name": "tool_call_search",
                "input": {"q": "project status"},
                "output": "Project on track for Q3",
                "startTime": "2024-06-15T10:00:01Z",
                "endTime": "2024-06-15T10:00:02Z",
            },
            {
                "id": "obs-llm",
                "traceId": "trace-1",
                "parentObservationId": "obs-root",
                "type": "GENERATION",
                "name": "gpt-4o",
                "input": "Summarise the status",
                "output": "Project is on track",
                "model": "gpt-4o",
                "usage": {"input": 50, "output": 30, "total": 80},
                "startTime": "2024-06-15T10:00:03Z",
                "endTime": "2024-06-15T10:00:05Z",
            },
        ]

        trace = from_langfuse(observations)
        assert isinstance(trace, Trace)
        assert trace.id == "trace-1"
        assert trace.input == {"query": "What is the status?"}
        assert trace.output == "Project is on track"
        assert len(trace.spans) == 1  # root only
        root = trace.spans[0]
        assert root.type == SpanType.AGENT_STEP
        assert len(root.children) == 2
        assert root.children[1].type == SpanType.LLM_CALL
        assert root.children[1].metadata.get("model") == "gpt-4o"
        assert root.children[1].metadata.get("token_usage") == {"input": 50, "output": 30, "total": 80}

    def test_tool_observation_type(self):
        observations = [
            {
                "id": "t1",
                "traceId": "t",
                "type": "TOOL",
                "name": "web_search",
                "input": {"query": "latest news"},
                "output": "Results found",
            },
        ]
        trace = from_langfuse(observations)
        assert trace.spans[0].type == SpanType.TOOL_CALL
        assert trace.spans[0].tool_call is not None
        assert trace.spans[0].tool_call.name == "web_search"

    def test_name_based_type_inference(self):
        observations = [
            {"id": "r1", "traceId": "t", "name": "rag_retrieval", "input": {"q": "x"}, "output": "docs"},
        ]
        trace = from_langfuse(observations)
        assert trace.spans[0].type == SpanType.RETRIEVAL
        assert trace.spans[0].tool_call is not None
        assert trace.spans[0].tool_call.name == "rag_retrieval"

    def test_empty_observations(self):
        trace = from_langfuse([])
        assert isinstance(trace, Trace)
        assert len(trace.spans) == 0

    def test_error_level_detected(self):
        observations = [
            {
                "id": "e1",
                "traceId": "t",
                "name": "failing_step",
                "level": "ERROR",
                "statusMessage": "Connection timeout",
            },
        ]
        trace = from_langfuse(observations)
        assert trace.spans[0].error == "Connection timeout"

    def test_snake_case_keys(self):
        observations = [
            {
                "id": "s1",
                "trace_id": "trace-snake",
                "parent_observation_id": None,
                "name": "root",
                "start_time": "2024-01-01T00:00:00Z",
                "end_time": "2024-01-01T00:01:00Z",
                "input": "hello",
                "output": "world",
            },
        ]
        trace = from_langfuse(observations)
        assert trace.id == "trace-snake"
        assert len(trace.spans) == 1

    def test_override_trace_id(self):
        observations = [
            {"id": "o1", "traceId": "original", "name": "span1"},
        ]
        trace = from_langfuse(observations, trace_id="overridden")
        assert trace.id == "overridden"

    def test_deep_nesting(self):
        observations = [
            {"id": "root", "traceId": "t", "name": "chain", "type": "SPAN"},
            {"id": "mid", "traceId": "t", "parentObservationId": "root", "name": "sub_agent", "type": "SPAN"},
            {"id": "leaf", "traceId": "t", "parentObservationId": "mid", "name": "tool_call", "type": "TOOL",
             "input": {"x": 1}, "output": "done"},
        ]
        trace = from_langfuse(observations)
        assert len(trace.spans) == 1
        assert len(trace.spans[0].children) == 1
        assert len(trace.spans[0].children[0].children) == 1
        leaf = trace.spans[0].children[0].children[0]
        assert leaf.type == SpanType.TOOL_CALL
        assert leaf.tool_call.result == "done"


class TestLangfuseLegacyTrace:
    """Tests for the legacy trace dict input path."""

    def test_legacy_trace_dict(self):
        trace_dict = {
            "id": "legacy-1",
            "input": "What is the weather?",
            "output": "Sunny and warm",
            "metadata": {"session_id": "s-123"},
            "observations": [
                {
                    "id": "obs-1",
                    "name": "weather_tool",
                    "type": "TOOL",
                    "input": {"city": "London"},
                    "output": "Sunny, 22C",
                    "startTime": "2024-06-15T10:00:00Z",
                },
                {
                    "id": "obs-2",
                    "parentObservationId": "obs-1",
                    "name": "gpt-4",
                    "type": "GENERATION",
                    "input": "Summarise weather",
                    "output": "Sunny and warm",
                    "model": "gpt-4",
                    "startTime": "2024-06-15T10:00:01Z",
                },
            ],
        }
        trace = from_langfuse(trace_dict)
        assert trace.id == "legacy-1"
        assert trace.input == "What is the weather?"
        assert trace.output == "Sunny and warm"
        assert trace.metadata == {"session_id": "s-123"}
        assert len(trace.spans) == 1  # root: obs-1
        assert len(trace.spans[0].children) == 1  # child: obs-2

    def test_legacy_empty_observations(self):
        trace_dict = {
            "id": "empty-trace",
            "input": "test",
            "output": "result",
            "observations": [],
        }
        trace = from_langfuse(trace_dict)
        assert trace.id == "empty-trace"
        assert len(trace.spans) == 0

    def test_legacy_no_observations_key(self):
        trace_dict = {"id": "no-obs", "input": "q", "output": "a"}
        trace = from_langfuse(trace_dict)
        assert trace.id == "no-obs"
        assert len(trace.spans) == 0


class TestLangfuseSDKObjects:
    """Test that SDK-like objects with model_dump() are handled."""

    def test_objects_with_model_dump(self):
        class FakeObservation:
            def model_dump(self, mode="json"):
                return {
                    "id": "sdk-1",
                    "traceId": "t-sdk",
                    "name": "tool_search",
                    "type": "TOOL",
                    "input": {"q": "test"},
                    "output": "found",
                    "startTime": "2024-01-01T00:00:00Z",
                }

        trace = from_langfuse([FakeObservation()])
        assert trace.id == "t-sdk"
        assert trace.spans[0].type == SpanType.TOOL_CALL
        assert trace.spans[0].tool_call.name == "tool_search"
