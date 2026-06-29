"""Tests for the LangGraph adapter."""

import pytest

from scora.adapters import from_langgraph
from scora.models import SpanType, Trace


class TestLangGraphFromMessages:
    """Tests for the LangGraph state/messages input path."""

    def test_basic_state_with_messages(self):
        state = {
            "messages": [
                {"type": "human", "content": "What is the weather?"},
                {
                    "type": "ai",
                    "content": "Let me check the weather.",
                    "tool_calls": [
                        {"name": "get_weather", "args": {"city": "London"}},
                    ],
                    "response_metadata": {"model_name": "gpt-4o"},
                },
                {
                    "type": "tool",
                    "name": "get_weather",
                    "content": "Sunny, 22°C",
                    "tool_call_id": "tc-1",
                },
                {
                    "type": "ai",
                    "content": "The weather in London is sunny and 22°C.",
                    "response_metadata": {"model_name": "gpt-4o"},
                },
            ],
        }

        trace = from_langgraph(state)
        assert isinstance(trace, Trace)
        assert trace.input == "What is the weather?"
        assert trace.output == "The weather in London is sunny and 22°C."

        llm_spans = [s for s in trace.spans if s.type == SpanType.LLM_CALL]
        tool_spans = [s for s in trace.spans if s.type == SpanType.TOOL_CALL]
        assert len(llm_spans) == 2
        assert len(tool_spans) == 1
        assert tool_spans[0].tool_call.name == "get_weather"
        assert tool_spans[0].tool_call.result == "Sunny, 22°C"

    def test_message_list_directly(self):
        messages = [
            {"role": "human", "content": "Hello"},
            {"role": "ai", "content": "Hi there!"},
        ]
        trace = from_langgraph(messages)
        assert trace.input == "Hello"
        assert trace.output == "Hi there!"
        assert len(trace.spans) == 1
        assert trace.spans[0].type == SpanType.LLM_CALL

    def test_ai_message_with_tool_calls_no_content(self):
        state = {
            "messages": [
                {"type": "human", "content": "Calculate 2+2"},
                {
                    "type": "ai",
                    "content": "",
                    "tool_calls": [
                        {"name": "calculator", "args": {"expression": "2+2"}},
                    ],
                },
                {"type": "tool", "name": "calculator", "content": "4"},
                {"type": "ai", "content": "The answer is 4."},
            ],
        }
        trace = from_langgraph(state)
        assert trace.output == "The answer is 4."

        tool_call_spans = []
        for s in trace.spans:
            if s.type == SpanType.TOOL_CALL:
                tool_call_spans.append(s)
            for c in s.children:
                if c.type == SpanType.TOOL_CALL:
                    tool_call_spans.append(c)

        assert any(tc.tool_call and tc.tool_call.name == "calculator" for tc in tool_call_spans)

    def test_empty_messages(self):
        trace = from_langgraph({"messages": []})
        assert isinstance(trace, Trace)
        assert len(trace.spans) == 0

    def test_empty_state_no_messages(self):
        trace = from_langgraph({})
        assert isinstance(trace, Trace)

    def test_tool_error(self):
        state = {
            "messages": [
                {"type": "human", "content": "test"},
                {"type": "tool", "name": "broken_tool", "content": "Connection refused", "status": "error"},
            ],
        }
        trace = from_langgraph(state)
        tool_spans = [s for s in trace.spans if s.type == SpanType.TOOL_CALL]
        assert len(tool_spans) == 1
        assert tool_spans[0].error == "Connection refused"

    def test_override_trace_id(self):
        trace = from_langgraph(
            {"messages": [{"type": "human", "content": "hi"}]},
            trace_id="custom-123",
        )
        assert trace.id == "custom-123"

    def test_model_metadata_extraction(self):
        state = {
            "messages": [
                {"type": "human", "content": "test"},
                {
                    "type": "ai",
                    "content": "response",
                    "response_metadata": {"model_name": "gemini-2.0-flash"},
                    "usage_metadata": {"input_tokens": 10, "output_tokens": 20},
                },
            ],
        }
        trace = from_langgraph(state)
        llm_span = trace.spans[0]
        assert llm_span.metadata.get("model") == "gemini-2.0-flash"
        assert llm_span.metadata.get("token_usage") == {"input_tokens": 10, "output_tokens": 20}

    def test_json_string_tool_args(self):
        state = {
            "messages": [
                {"type": "human", "content": "test"},
                {
                    "type": "ai",
                    "content": "",
                    "tool_calls": [
                        {"name": "search", "args": '{"query": "test"}'},
                    ],
                },
            ],
        }
        trace = from_langgraph(state)
        llm_span = trace.spans[0]
        assert len(llm_span.children) == 1
        assert llm_span.children[0].tool_call.arguments == {"query": "test"}


class TestLangGraphFromEvents:
    """Tests for the astream_events input path."""

    def test_streaming_events(self):
        events = [
            {
                "event": "on_chain_start",
                "name": "agent",
                "data": {"input": {"messages": [{"content": "What is AI?"}]}},
                "run_id": "run-1",
            },
            {
                "event": "on_tool_start",
                "name": "web_search",
                "data": {"input": {"query": "what is AI"}},
                "run_id": "run-2",
            },
            {
                "event": "on_tool_end",
                "name": "web_search",
                "data": {"output": {"content": "AI is artificial intelligence."}},
                "run_id": "run-2",
            },
            {
                "event": "on_chat_model_end",
                "name": "gpt-4o",
                "data": {
                    "output": {
                        "content": "AI stands for Artificial Intelligence.",
                        "response_metadata": {"model_name": "gpt-4o"},
                        "usage_metadata": {"input_tokens": 50, "output_tokens": 30},
                        "tool_calls": [],
                    },
                },
                "run_id": "run-3",
            },
        ]

        trace = from_langgraph(events)
        assert trace.input == "What is AI?"
        assert trace.output == "AI stands for Artificial Intelligence."

        tool_spans = [s for s in trace.spans if s.type == SpanType.TOOL_CALL]
        llm_spans = [s for s in trace.spans if s.type == SpanType.LLM_CALL]
        assert len(tool_spans) >= 1
        assert len(llm_spans) >= 1
        assert tool_spans[0].tool_call.name == "web_search"

    def test_empty_events(self):
        trace = from_langgraph([])
        assert isinstance(trace, Trace)

    def test_retriever_event(self):
        events = [
            {
                "event": "on_retriever_end",
                "name": "vector_store",
                "data": {
                    "input": {"query": "find docs"},
                    "output": [{"page_content": "doc1"}],
                },
                "run_id": "r1",
            },
        ]
        trace = from_langgraph(events)
        assert len(trace.spans) == 1
        assert trace.spans[0].type == SpanType.RETRIEVAL
