"""Tests for YAML configuration loading."""

import os
import tempfile
from pathlib import Path

import pytest

from agentic_eval.config import EvalConfig, load_config, _expand_env, _parse_config


class TestExpandEnv:
    def test_simple_var(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        assert _expand_env("Bearer ${MY_TOKEN}") == "Bearer secret123"

    def test_missing_var_unchanged(self):
        result = _expand_env("${NONEXISTENT_VAR_XYZ}")
        assert result == "${NONEXISTENT_VAR_XYZ}"

    def test_no_vars(self):
        assert _expand_env("plain text") == "plain text"

    def test_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "8000")
        assert _expand_env("http://${HOST}:${PORT}") == "http://localhost:8000"


class TestParseConfig:
    def test_minimal_config(self):
        raw = {"project": "test-project"}
        cfg = _parse_config(raw)
        assert isinstance(cfg, EvalConfig)
        assert cfg.project == "test-project"
        assert cfg.skills == []
        assert cfg.test_cases == []

    def test_full_config(self):
        raw = {
            "project": "my-agent",
            "skills": [
                {"path": "./SKILL.md", "thresholds": {"task_completion": 0.9}},
            ],
            "metrics": {
                "enabled": ["task_completion", "groundedness"],
                "weights": {"task_completion": 0.5},
                "use_llm_judge": True,
            },
            "agent": {
                "url": "http://localhost:8000/api",
                "method": "POST",
                "headers": {"Authorization": "Bearer token"},
                "body_template": {"query": "${query}"},
                "timeout": 30.0,
                "response_path": "output.text",
            },
            "test_cases": [
                {
                    "input": "hello",
                    "expected_output": "world",
                    "expected_tools": ["search"],
                    "skill": "./custom.md",
                    "tags": ["smoke"],
                },
            ],
            "ci": {
                "fail_below": 0.7,
                "fail_on_any_metric_below": 0.4,
                "save": False,
                "db_path": "./custom.db",
                "output_format": "json",
                "output_file": "./report.json",
            },
        }
        cfg = _parse_config(raw)
        assert cfg.project == "my-agent"
        assert len(cfg.skills) == 1
        assert cfg.skills[0].thresholds == {"task_completion": 0.9}
        assert cfg.metrics.enabled == ["task_completion", "groundedness"]
        assert cfg.metrics.use_llm_judge is True
        assert cfg.agent.url == "http://localhost:8000/api"
        assert cfg.agent.response_path == "output.text"
        assert len(cfg.test_cases) == 1
        assert cfg.test_cases[0].expected_tools == ["search"]
        assert cfg.ci.fail_below == 0.7
        assert cfg.ci.output_file == "./report.json"

    def test_has_agent_property(self):
        cfg = _parse_config({"agent": {"url": "http://test"}})
        assert cfg.has_agent is True

        cfg_no = _parse_config({})
        assert cfg_no.has_agent is False

    def test_has_test_cases_property(self):
        cfg = _parse_config({"test_cases": [{"input": "x"}]})
        assert cfg.has_test_cases is True

        cfg_no = _parse_config({})
        assert cfg_no.has_test_cases is False


class TestLoadConfig:
    def test_load_from_file(self, tmp_path):
        pytest.importorskip("yaml")
        config_file = tmp_path / "agentic-eval.yaml"
        config_file.write_text(
            "project: test\n"
            "skills:\n"
            "  - path: ./SKILL.md\n"
            "    thresholds:\n"
            "      task_completion: 0.9\n"
            "test_cases:\n"
            "  - input: hello\n"
        )
        cfg = load_config(config_file)
        assert cfg.project == "test"
        assert len(cfg.skills) == 1
        assert len(cfg.test_cases) == 1

    def test_env_interpolation_in_file(self, tmp_path, monkeypatch):
        pytest.importorskip("yaml")
        monkeypatch.setenv("MY_URL", "http://localhost:9000")
        config_file = tmp_path / "agentic-eval.yaml"
        config_file.write_text(
            "project: test\n"
            "agent:\n"
            "  url: ${MY_URL}/api\n"
        )
        cfg = load_config(config_file)
        assert cfg.agent.url == "http://localhost:9000/api"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_auto_find_disabled_in_test(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError):
            load_config()


class TestAgentEvaluator:
    def test_build_request(self):
        from agentic_eval.agent_evaluator import AgentEvaluator

        evaluator = AgentEvaluator(
            url="http://localhost:8000/threads/{thread_id}/runs",
            headers={"Authorization": "Bearer token"},
            body_template={
                "assistant_id": "test",
                "input": {"messages": [{"role": "user", "content": "${query}"}]},
            },
        )
        url, headers, body = evaluator.build_request("hello world", thread_id="t-123")
        assert url == "http://localhost:8000/threads/t-123/runs"
        assert headers["Authorization"] == "Bearer token"
        assert body["input"]["messages"][0]["content"] == "hello world"

    def test_build_request_generates_thread_id(self):
        from agentic_eval.agent_evaluator import AgentEvaluator

        evaluator = AgentEvaluator(url="http://test/{thread_id}")
        url, _, _ = evaluator.build_request("test")
        assert "{thread_id}" not in url

    def test_response_to_trace(self):
        from agentic_eval.agent_evaluator import AgentEvaluator
        from datetime import datetime, timezone

        evaluator = AgentEvaluator()
        response = {
            "status_code": 200,
            "body": {"output": "The answer is 42", "messages": []},
            "raw_text": '{"output": "The answer is 42"}',
            "elapsed_ms": 150.0,
            "started_at": datetime.now(timezone.utc),
            "ended_at": datetime.now(timezone.utc),
        }
        trace = evaluator.response_to_trace("what is the answer?", response)
        assert trace.input == "what is the answer?"
        assert trace.output == "The answer is 42"

    def test_response_path_extraction(self):
        from agentic_eval.agent_evaluator import AgentEvaluator
        from datetime import datetime, timezone

        evaluator = AgentEvaluator(response_path="data.result.text")
        response = {
            "status_code": 200,
            "body": {"data": {"result": {"text": "deep value"}}},
            "raw_text": "...",
            "started_at": datetime.now(timezone.utc),
            "ended_at": datetime.now(timezone.utc),
        }
        trace = evaluator.response_to_trace("query", response)
        assert trace.output == "deep value"

    def test_from_config(self):
        from agentic_eval.agent_evaluator import from_config, AgentEvaluator
        from agentic_eval.config import EvalConfig, AgentConfig

        cfg = EvalConfig(
            agent=AgentConfig(
                url="http://test/api",
                headers={"X-Key": "val"},
                timeout=45.0,
            ),
        )
        evaluator = from_config(cfg)
        assert isinstance(evaluator, AgentEvaluator)
        assert evaluator.url == "http://test/api"
        assert evaluator.timeout == 45.0

    def test_extract_spans_from_messages(self):
        from agentic_eval.agent_evaluator import AgentEvaluator
        from datetime import datetime, timezone

        evaluator = AgentEvaluator()
        response = {
            "status_code": 200,
            "body": {
                "output": "result",
                "messages": [
                    {"role": "user", "content": "query"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {"name": "search", "args": {"q": "test"}},
                        ],
                    },
                    {"role": "tool", "name": "search", "content": "found it"},
                    {"role": "assistant", "content": "Here is the result"},
                ],
            },
            "raw_text": "...",
            "started_at": datetime.now(timezone.utc),
            "ended_at": datetime.now(timezone.utc),
        }
        trace = evaluator.response_to_trace("query", response)
        assert len(trace.spans) >= 2
        tool_spans = [s for s in trace.spans if s.tool_call and s.tool_call.name == "search"]
        assert len(tool_spans) >= 1
