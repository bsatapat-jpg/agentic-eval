"""Tests for framework adapters."""

from datetime import datetime, timezone

import pytest

from scora.adapters import from_langchain, from_openai, from_otel
from scora.models import SpanType, Trace


class TestLangChainAdapter:
    def test_basic_run(self):
        run = {
            "id": "run-1",
            "inputs": {"query": "hello"},
            "outputs": {"result": "world"},
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:01:00Z",
            "child_runs": [
                {
                    "id": "child-1",
                    "name": "search",
                    "run_type": "tool",
                    "inputs": {"q": "hello"},
                    "outputs": "found it",
                    "start_time": "2024-01-01T00:00:10Z",
                    "end_time": "2024-01-01T00:00:20Z",
                    "child_runs": [],
                },
                {
                    "id": "child-2",
                    "name": "gpt-4",
                    "run_type": "llm",
                    "inputs": "generate response",
                    "outputs": "world",
                    "start_time": "2024-01-01T00:00:20Z",
                    "end_time": "2024-01-01T00:00:50Z",
                    "child_runs": [],
                },
            ],
        }

        trace = from_langchain(run)
        assert isinstance(trace, Trace)
        assert trace.id == "run-1"
        assert len(trace.spans) == 2
        assert trace.spans[0].type == SpanType.TOOL_CALL
        assert trace.spans[1].type == SpanType.LLM_CALL
        assert trace.spans[0].tool_call is not None
        assert trace.spans[0].tool_call.name == "search"

    def test_empty_run(self):
        run = {"id": "empty", "child_runs": []}
        trace = from_langchain(run)
        assert isinstance(trace, Trace)
        assert len(trace.spans) == 0

    def test_nested_children(self):
        run = {
            "id": "nested",
            "child_runs": [
                {
                    "id": "parent",
                    "name": "agent",
                    "run_type": "agent",
                    "child_runs": [
                        {
                            "id": "inner",
                            "name": "tool_x",
                            "run_type": "tool",
                            "child_runs": [],
                        },
                    ],
                },
            ],
        }
        trace = from_langchain(run)
        assert len(trace.spans) == 1
        assert len(trace.spans[0].children) == 1
        assert trace.spans[0].children[0].type == SpanType.TOOL_CALL


class TestOpenAIAdapter:
    def test_basic_conversation(self):
        messages = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
        ]
        trace = from_openai(messages)
        assert isinstance(trace, Trace)
        assert trace.input == "What is 2+2?"
        assert trace.output == "4"
        assert len(trace.spans) == 1

    def test_with_tool_calls(self):
        messages = [
            {"role": "user", "content": "Calculate something"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc1",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expr": "2+2"}',
                        },
                    },
                ],
            },
            {"role": "tool", "content": "4", "tool_call_id": "tc1"},
            {"role": "assistant", "content": "The answer is 4"},
        ]
        trace = from_openai(messages)
        assert trace.input == "Calculate something"
        assert trace.output == "The answer is 4"
        tool_spans = [s for s in trace.spans if s.type == SpanType.TOOL_CALL]
        assert len(tool_spans) >= 1

    def test_empty_messages(self):
        trace = from_openai([])
        assert isinstance(trace, Trace)
        assert trace.input is None


class TestOTelAdapter:
    def test_basic_spans(self):
        spans = [
            {
                "traceId": "trace-1",
                "spanId": "span-1",
                "name": "agent_run",
                "startTimeUnixNano": 1700000000000000000,
                "endTimeUnixNano": 1700000001000000000,
                "attributes": {},
                "status": {},
            },
            {
                "traceId": "trace-1",
                "spanId": "span-2",
                "parentSpanId": "span-1",
                "name": "tool:read_file",
                "startTimeUnixNano": 1700000000100000000,
                "endTimeUnixNano": 1700000000500000000,
                "attributes": {"tool.name": "read_file"},
                "status": {},
            },
        ]
        trace = from_otel(spans)
        assert isinstance(trace, Trace)
        assert trace.id == "trace-1"
        assert len(trace.spans) == 1
        assert len(trace.spans[0].children) == 1
        assert trace.spans[0].children[0].type == SpanType.TOOL_CALL

    def test_empty_spans(self):
        trace = from_otel([])
        assert isinstance(trace, Trace)

    def test_llm_span(self):
        spans = [
            {
                "traceId": "t1",
                "spanId": "s1",
                "name": "llm_call",
                "startTimeUnixNano": 1700000000000000000,
                "endTimeUnixNano": 1700000001000000000,
                "attributes": {"gen_ai.system": "openai"},
                "status": {},
            },
        ]
        trace = from_otel(spans)
        assert trace.spans[0].type == SpanType.LLM_CALL
