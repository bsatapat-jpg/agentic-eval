"""Tests for the MLflow adapter."""

from datetime import datetime, timezone

import pytest

from scora.adapters import from_mlflow
from scora.models import SpanType, Trace


class TestMLflowSpanList:
    """Tests for the plain span-list input path."""

    def test_basic_span_list(self):
        spans = [
            {
                "span_id": "root-1",
                "trace_id": "trace-1",
                "parent_id": None,
                "name": "agent_workflow",
                "span_type": "AGENT",
                "start_time_ns": 1700000000000000000,
                "end_time_ns": 1700000005000000000,
                "inputs": {"query": "summarise report"},
                "outputs": {"result": "Report summary"},
                "status": {"status_code": "OK"},
                "attributes": {},
                "events": [],
            },
            {
                "span_id": "tool-1",
                "trace_id": "trace-1",
                "parent_id": "root-1",
                "name": "read_file",
                "span_type": "TOOL",
                "start_time_ns": 1700000001000000000,
                "end_time_ns": 1700000002000000000,
                "inputs": {"path": "/data/report.csv"},
                "outputs": "col1,col2\n1,2",
                "status": {"status_code": "OK"},
                "attributes": {},
                "events": [],
            },
            {
                "span_id": "llm-1",
                "trace_id": "trace-1",
                "parent_id": "root-1",
                "name": "gpt-4o",
                "span_type": "CHAT_MODEL",
                "start_time_ns": 1700000003000000000,
                "end_time_ns": 1700000005000000000,
                "inputs": {"messages": [{"role": "user", "content": "summarise"}]},
                "outputs": {"content": "Report summary"},
                "status": {"status_code": "OK"},
                "attributes": {"mlflow.chat.model": "gpt-4o"},
                "events": [],
            },
        ]

        trace = from_mlflow(spans)
        assert isinstance(trace, Trace)
        assert trace.id == "trace-1"
        assert trace.input == {"query": "summarise report"}
        assert trace.output == {"result": "Report summary"}
        assert len(trace.spans) == 1  # root only
        root = trace.spans[0]
        assert root.type == SpanType.AGENT_STEP
        assert len(root.children) == 2

        tool_span = root.children[0]
        assert tool_span.type == SpanType.TOOL_CALL
        assert tool_span.tool_call is not None
        assert tool_span.tool_call.name == "read_file"
        assert tool_span.tool_call.arguments == {"path": "/data/report.csv"}

        llm_span = root.children[1]
        assert llm_span.type == SpanType.LLM_CALL
        assert llm_span.metadata.get("model") == "gpt-4o"

    def test_retriever_span(self):
        spans = [
            {
                "span_id": "ret-1",
                "trace_id": "t1",
                "name": "vector_search",
                "span_type": "RETRIEVER",
                "inputs": {"query": "find relevant docs"},
                "outputs": [{"page_content": "doc1", "metadata": {}}],
                "start_time_ns": 1700000000000000000,
                "end_time_ns": 1700000001000000000,
            },
        ]
        trace = from_mlflow(spans)
        assert trace.spans[0].type == SpanType.RETRIEVAL
        assert trace.spans[0].tool_call is not None
        assert trace.spans[0].tool_call.name == "vector_search"

    def test_all_span_types(self):
        type_map = {
            "TOOL": SpanType.TOOL_CALL,
            "RETRIEVER": SpanType.RETRIEVAL,
            "LLM": SpanType.LLM_CALL,
            "CHAT_MODEL": SpanType.LLM_CALL,
            "AGENT": SpanType.AGENT_STEP,
            "CHAIN": SpanType.AGENT_STEP,
            "WORKFLOW": SpanType.AGENT_STEP,
            "TASK": SpanType.AGENT_STEP,
            "EMBEDDING": SpanType.LLM_CALL,
            "PARSER": SpanType.CUSTOM,
            "RERANKER": SpanType.CUSTOM,
            "MEMORY": SpanType.CUSTOM,
            "GUARDRAIL": SpanType.CUSTOM,
            "EVALUATOR": SpanType.CUSTOM,
            "UNKNOWN": SpanType.CUSTOM,
        }
        for mlflow_type, expected in type_map.items():
            spans = [{"span_id": f"s-{mlflow_type}", "trace_id": "t", "name": "x", "span_type": mlflow_type}]
            trace = from_mlflow(spans)
            assert trace.spans[0].type == expected, f"Failed for {mlflow_type}"

    def test_empty_span_list(self):
        trace = from_mlflow([])
        assert isinstance(trace, Trace)
        assert len(trace.spans) == 0

    def test_error_status(self):
        spans = [
            {
                "span_id": "err-1",
                "trace_id": "t",
                "name": "failing",
                "span_type": "TOOL",
                "status": {"status_code": "ERROR", "description": "Connection refused"},
            },
        ]
        trace = from_mlflow(spans)
        assert trace.spans[0].error == "Connection refused"

    def test_exception_event(self):
        spans = [
            {
                "span_id": "exc-1",
                "trace_id": "t",
                "name": "crashing",
                "span_type": "TOOL",
                "status": {"status_code": "OK"},
                "events": [
                    {
                        "name": "exception",
                        "attributes": {
                            "exception.type": "ValueError",
                            "exception.message": "Invalid input",
                        },
                    },
                ],
            },
        ]
        trace = from_mlflow(spans)
        assert trace.spans[0].error == "Invalid input"

    def test_override_trace_id(self):
        spans = [{"span_id": "s1", "trace_id": "original", "name": "x"}]
        trace = from_mlflow(spans, trace_id="custom-id")
        assert trace.id == "custom-id"

    def test_deep_nesting(self):
        spans = [
            {"span_id": "root", "trace_id": "t", "name": "agent", "span_type": "AGENT"},
            {"span_id": "mid", "trace_id": "t", "parent_id": "root", "name": "chain", "span_type": "CHAIN"},
            {"span_id": "leaf", "trace_id": "t", "parent_id": "mid", "name": "tool_x", "span_type": "TOOL",
             "inputs": {"k": "v"}, "outputs": "done"},
        ]
        trace = from_mlflow(spans)
        assert len(trace.spans) == 1
        assert len(trace.spans[0].children) == 1
        assert len(trace.spans[0].children[0].children) == 1
        leaf = trace.spans[0].children[0].children[0]
        assert leaf.type == SpanType.TOOL_CALL
        assert leaf.tool_call.result == "done"


class TestMLflowTraceDict:
    """Tests for the serialised trace dict input path."""

    def test_trace_dict_with_info_and_data(self):
        trace_dict = {
            "info": {
                "trace_id": "dict-trace-1",
                "timestamp_ms": 1700000000000,
                "execution_time_ms": 5000,
                "tags": {"env": "test"},
            },
            "data": {
                "spans": [
                    {
                        "span_id": "s1",
                        "name": "main_agent",
                        "span_type": "AGENT",
                        "inputs": {"query": "hello"},
                        "outputs": {"answer": "hi"},
                        "start_time_ns": 1700000000000000000,
                        "end_time_ns": 1700000005000000000,
                    },
                    {
                        "span_id": "s2",
                        "parent_id": "s1",
                        "name": "search_tool",
                        "span_type": "TOOL",
                        "inputs": {"q": "hello"},
                        "outputs": "result",
                        "start_time_ns": 1700000001000000000,
                        "end_time_ns": 1700000002000000000,
                    },
                ],
            },
        }
        trace = from_mlflow(trace_dict)
        assert trace.id == "dict-trace-1"
        assert trace.input == {"query": "hello"}
        assert trace.output == {"answer": "hi"}
        assert len(trace.spans) == 1
        assert len(trace.spans[0].children) == 1

    def test_empty_trace_dict(self):
        trace_dict = {"info": {}, "data": {"spans": []}}
        trace = from_mlflow(trace_dict)
        assert isinstance(trace, Trace)
        assert len(trace.spans) == 0


class TestMLflowTraceObject:
    """Tests for the MLflow Trace SDK object input path."""

    def test_trace_object(self):
        class FakeSpan:
            def to_dict(self):
                return {
                    "span_id": "obj-s1",
                    "trace_id": "obj-trace",
                    "name": "rag_retrieval",
                    "span_type": "RETRIEVER",
                    "inputs": {"query": "find docs"},
                    "outputs": [{"page_content": "doc1"}],
                    "start_time_ns": 1700000000000000000,
                    "end_time_ns": 1700000001000000000,
                }

        class FakeInfo:
            trace_id = "obj-trace"
            timestamp_ms = 1700000000000
            execution_time_ms = 2000
            experiment_id = "exp-1"
            tags = {"version": "1.0"}

        class FakeData:
            spans = [FakeSpan()]

        class FakeTrace:
            info = FakeInfo()
            data = FakeData()

        trace = from_mlflow(FakeTrace())
        assert trace.id == "obj-trace"
        assert len(trace.spans) == 1
        assert trace.spans[0].type == SpanType.RETRIEVAL
        assert trace.spans[0].tool_call.name == "rag_retrieval"
        assert trace.metadata.get("experiment_id") == "exp-1"

    def test_name_based_inference(self):
        spans = [
            {"span_id": "s1", "trace_id": "t", "name": "vector_search_retrieval", "span_type": "UNKNOWN"},
        ]
        trace = from_mlflow(spans)
        assert trace.spans[0].type == SpanType.RETRIEVAL

    def test_name_based_llm_inference(self):
        spans = [
            {"span_id": "s1", "trace_id": "t", "name": "gpt-4o-mini", "span_type": "UNKNOWN"},
        ]
        trace = from_mlflow(spans)
        assert trace.spans[0].type == SpanType.LLM_CALL
