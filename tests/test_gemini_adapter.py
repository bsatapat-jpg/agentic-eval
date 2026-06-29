"""Tests for the Gemini adapter."""

import pytest

from skora.adapters import from_gemini
from skora.models import SpanType, Trace


class TestGeminiBasicConversation:
    def test_simple_text_exchange(self):
        contents = [
            {"role": "user", "parts": [{"text": "What is 2+2?"}]},
            {"role": "model", "parts": [{"text": "4"}]},
        ]
        trace = from_gemini(contents)
        assert isinstance(trace, Trace)
        assert trace.input == "What is 2+2?"
        assert trace.output == "4"
        assert len(trace.spans) == 1
        assert trace.spans[0].type == SpanType.LLM_CALL

    def test_multi_turn(self):
        contents = [
            {"role": "user", "parts": [{"text": "Hello"}]},
            {"role": "model", "parts": [{"text": "Hi there!"}]},
            {"role": "user", "parts": [{"text": "How are you?"}]},
            {"role": "model", "parts": [{"text": "I'm doing well!"}]},
        ]
        trace = from_gemini(contents)
        assert trace.input == "Hello"
        assert trace.output == "I'm doing well!"
        assert len(trace.spans) == 2

    def test_empty_contents(self):
        trace = from_gemini([])
        assert isinstance(trace, Trace)
        assert trace.input is None
        assert trace.output is None


class TestGeminiFunctionCalling:
    def test_function_call_in_parts(self):
        contents = [
            {"role": "user", "parts": [{"text": "Search for Python tutorials"}]},
            {
                "role": "model",
                "parts": [
                    {"text": "Let me search for that."},
                    {"functionCall": {"name": "search", "args": {"query": "Python tutorials"}}},
                ],
            },
            {
                "role": "function",
                "parts": [
                    {
                        "functionResponse": {
                            "name": "search",
                            "response": {"results": ["tutorial1", "tutorial2"]},
                        }
                    }
                ],
            },
            {"role": "model", "parts": [{"text": "Here are some tutorials I found."}]},
        ]
        trace = from_gemini(contents)
        assert trace.input == "Search for Python tutorials"
        assert trace.output == "Here are some tutorials I found."
        assert len(trace.spans) == 3

        model_span = trace.spans[0]
        assert model_span.type == SpanType.LLM_CALL
        assert len(model_span.children) == 1
        assert model_span.children[0].type == SpanType.TOOL_CALL
        assert model_span.children[0].tool_call.name == "search"
        assert model_span.children[0].tool_call.arguments == {"query": "Python tutorials"}

        func_resp_span = trace.spans[1]
        assert func_resp_span.type == SpanType.TOOL_CALL
        assert func_resp_span.tool_call.name == "search"
        assert func_resp_span.tool_call.result == {"results": ["tutorial1", "tutorial2"]}

    def test_multiple_function_calls(self):
        contents = [
            {"role": "user", "parts": [{"text": "Get weather and news"}]},
            {
                "role": "model",
                "parts": [
                    {"functionCall": {"name": "get_weather", "args": {"city": "NYC"}}},
                    {"functionCall": {"name": "get_news", "args": {"topic": "tech"}}},
                ],
            },
        ]
        trace = from_gemini(contents)
        model_span = trace.spans[0]
        assert len(model_span.children) == 2
        assert model_span.children[0].tool_call.name == "get_weather"
        assert model_span.children[1].tool_call.name == "get_news"

    def test_function_call_snake_case_format(self):
        """Handles the snake_case format used by newer SDK versions."""
        contents = [
            {"role": "user", "parts": [{"text": "Do something"}]},
            {
                "role": "model",
                "parts": [
                    {"function_call": {"name": "my_tool", "args": {"x": 1}}},
                ],
            },
            {
                "role": "function",
                "parts": [
                    {
                        "function_response": {
                            "name": "my_tool",
                            "response": {"result": "done"},
                        }
                    }
                ],
            },
        ]
        trace = from_gemini(contents)
        model_span = trace.spans[0]
        assert len(model_span.children) == 1
        assert model_span.children[0].tool_call.name == "my_tool"

        func_resp = trace.spans[1]
        assert func_resp.tool_call.name == "my_tool"


class TestGeminiResponseObject:
    def test_from_response_dict(self):
        response = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": "Hello from Gemini!"}],
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
                "totalTokenCount": 15,
            },
        }
        trace = from_gemini(response=response)
        assert trace.output == "Hello from Gemini!"
        assert trace.metadata["token_usage"]["prompt_tokens"] == 10
        assert trace.metadata["token_usage"]["total_tokens"] == 15

    def test_model_metadata(self):
        contents = [
            {"role": "user", "parts": [{"text": "Hi"}]},
            {"role": "model", "parts": [{"text": "Hello"}]},
        ]
        trace = from_gemini(contents, model="gemini-2.0-flash")
        assert trace.metadata["model"] == "gemini-2.0-flash"
        assert "gemini" in trace.spans[0].name


class TestGeminiSDKObjectHandling:
    def test_sdk_like_content_object(self):
        """Simulates SDK Content objects with .role and .parts attributes."""

        class FakePart:
            def __init__(self, text=None, function_call=None):
                self.text = text
                self.function_call = function_call

        class FakeContent:
            def __init__(self, role, parts):
                self.role = role
                self.parts = parts

        contents = [
            FakeContent("user", [FakePart(text="Hello")]),
            FakeContent("model", [FakePart(text="Hi there!")]),
        ]

        trace = from_gemini(contents)
        assert trace.input == "Hello"
        assert trace.output == "Hi there!"


class TestGeminiToolCallExtraction:
    def test_tool_calls_extracted_to_trace(self):
        contents = [
            {"role": "user", "parts": [{"text": "Read file.txt"}]},
            {
                "role": "model",
                "parts": [
                    {"functionCall": {"name": "read_file", "args": {"path": "file.txt"}}},
                ],
            },
            {
                "role": "function",
                "parts": [
                    {
                        "functionResponse": {
                            "name": "read_file",
                            "response": {"content": "file contents"},
                        }
                    }
                ],
            },
            {"role": "model", "parts": [{"text": "The file contains: file contents"}]},
        ]
        trace = from_gemini(contents)
        tool_calls = trace.tool_calls
        assert len(tool_calls) >= 1
        assert any(tc.name == "read_file" for tc in tool_calls)
