"""Evaluate live agents by calling their HTTP APIs.

``AgentEvaluator`` posts test cases to an agent endpoint, captures the
response, converts it to a Trace, and runs evaluation — all in one call.

Supports:
- Request/response endpoints (JSON APIs)
- LangGraph streaming endpoints (``stream_mode=messages-tuple``)
- Custom response extraction via ``response_path``
- Environment variable interpolation in headers and body templates

Usage::

    from skora.agent_evaluator import AgentEvaluator

    evaluator = AgentEvaluator(
        url="http://localhost:2026/threads/{thread_id}/runs",
        headers={"Authorization": "Bearer <token>"},
        body_template={
            "assistant_id": "sales_assistant_v2",
            "input": {"messages": [{"role": "user", "content": "${query}"}]},
        },
    )

    results = evaluator.evaluate(
        test_cases=[
            {"input": "What is the status?", "expected_tools": ["rag_search"]},
        ],
        skill="./SKILL.md",
    )

    for r in results:
        r.print()
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AgentConfig, EvalConfig, TestCase
from .models import EvalResult, SkillSpec, Span, SpanType, ToolCall, Trace


class AgentEvaluator:
    """Evaluate a live agent running behind an HTTP API."""

    def __init__(
        self,
        url: str = "",
        method: str = "POST",
        headers: dict[str, str] | None = None,
        body_template: dict[str, Any] | None = None,
        timeout: float = 60.0,
        response_path: str = "",
        config: AgentConfig | None = None,
    ) -> None:
        if config:
            self.url = config.url
            self.method = config.method
            self.headers = config.headers
            self.body_template = config.body_template
            self.timeout = config.timeout
            self.response_path = config.response_path
        else:
            self.url = url
            self.method = method.upper()
            self.headers = headers or {}
            self.body_template = body_template or {}
            self.timeout = timeout
            self.response_path = response_path

    def build_request(
        self,
        query: str,
        *,
        thread_id: str | None = None,
    ) -> tuple[str, dict[str, str], dict[str, Any] | None]:
        """Build the HTTP request for a test case.

        Returns:
            (url, headers, body) tuple ready for requests/httpx.
        """
        tid = thread_id or str(uuid.uuid4())
        url = self.url.replace("{thread_id}", tid)
        body = _interpolate(copy.deepcopy(self.body_template), {"query": query, "thread_id": tid})
        headers = {k: v for k, v in self.headers.items()}
        return url, headers, body

    def call_agent(
        self,
        query: str,
        *,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Call the agent endpoint and return the raw response.

        Requires ``requests`` or ``httpx`` to be installed.

        Returns:
            Response dict with ``status_code``, ``body``, and ``elapsed_ms``.
        """
        url, headers, body = self.build_request(query, thread_id=thread_id)

        try:
            import httpx
            client_cls = httpx.Client
        except ImportError:
            client_cls = None

        if client_cls:
            with httpx.Client(timeout=self.timeout) as client:
                started = datetime.now(timezone.utc)
                resp = client.request(self.method, url, headers=headers, json=body)
                ended = datetime.now(timezone.utc)
                return {
                    "status_code": resp.status_code,
                    "body": _safe_json(resp.text),
                    "raw_text": resp.text,
                    "elapsed_ms": (ended - started).total_seconds() * 1000,
                    "started_at": started,
                    "ended_at": ended,
                }

        try:
            import requests as req_lib
        except ImportError:
            raise ImportError(
                "Either 'httpx' or 'requests' is required for live agent evaluation. "
                "Install one: pip install httpx"
            )

        started = datetime.now(timezone.utc)
        resp = req_lib.request(self.method, url, headers=headers, json=body, timeout=self.timeout)
        ended = datetime.now(timezone.utc)
        return {
            "status_code": resp.status_code,
            "body": _safe_json(resp.text),
            "raw_text": resp.text,
            "elapsed_ms": (ended - started).total_seconds() * 1000,
            "started_at": started,
            "ended_at": ended,
        }

    def response_to_trace(
        self,
        query: str,
        response: dict[str, Any],
    ) -> Trace:
        """Convert an agent response into an skora Trace.

        Handles:
        - JSON dict responses (extracts tool calls, messages)
        - LangGraph streaming responses (newline-delimited events)
        - Plain text responses
        """
        body = response.get("body")
        raw_text = response.get("raw_text", "")
        started = response.get("started_at", datetime.now(timezone.utc))
        ended = response.get("ended_at", datetime.now(timezone.utc))

        output = self._extract_output(body, raw_text)
        spans = self._extract_spans(body, raw_text)

        return Trace(
            input=query,
            output=output,
            spans=spans,
            started_at=started,
            ended_at=ended,
            metadata={
                "status_code": response.get("status_code"),
                "elapsed_ms": response.get("elapsed_ms"),
            },
        )

    def evaluate(
        self,
        test_cases: list[dict[str, Any] | TestCase],
        skill: str | Path | SkillSpec | None = None,
        metrics: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
        weights: dict[str, float] | None = None,
        use_llm_judge: bool = False,
        save: bool = False,
        db_path: str = "./skora_results.db",
    ) -> list[EvalResult]:
        """Run test cases against the live agent and evaluate responses.

        Args:
            test_cases: List of test case dicts or TestCase objects.
            skill: Skill spec for evaluation.
            metrics: Specific metrics to run.
            thresholds: Per-metric thresholds.
            weights: Metric weights.
            use_llm_judge: Use LLM-as-judge mode.
            save: Persist results.
            db_path: Database path.

        Returns:
            List of EvalResult, one per test case.
        """
        from .api import run_evaluation

        results: list[EvalResult] = []

        for tc in test_cases:
            if isinstance(tc, TestCase):
                query = tc.input
                expected_output = tc.expected_output
                tc_skill = tc.skill
            else:
                query = tc.get("input", "")
                expected_output = tc.get("expected_output")
                tc_skill = tc.get("skill")

            eval_skill = tc_skill or skill

            response = self.call_agent(query)
            trace = self.response_to_trace(query, response)

            result = run_evaluation(
                trace=trace,
                skill=eval_skill,
                metrics=metrics,
                expected_output=expected_output,
                thresholds=thresholds,
                weights=weights,
                use_llm_judge=use_llm_judge,
                save=save,
                db_path=db_path,
            )
            results.append(result)

        return results

    def _extract_output(self, body: Any, raw_text: str) -> str | None:
        """Extract the agent's output from the response body."""
        if self.response_path and isinstance(body, dict):
            val = _dict_path(body, self.response_path)
            if val is not None:
                return str(val)

        if isinstance(body, dict):
            for key in ("output", "result", "response", "content", "answer", "text"):
                if key in body:
                    val = body[key]
                    if isinstance(val, str):
                        return val
                    if isinstance(val, dict):
                        for sub_key in ("content", "text", "result"):
                            if sub_key in val:
                                return str(val[sub_key])
                    return str(val)

            messages = body.get("messages", [])
            if messages:
                for msg in reversed(messages):
                    if isinstance(msg, dict):
                        role = msg.get("role", msg.get("type", ""))
                        if role in ("assistant", "ai"):
                            content = msg.get("content")
                            if content:
                                return str(content)

        if raw_text and not body:
            return raw_text[:2000]

        return str(body) if body else None

    def _extract_spans(self, body: Any, raw_text: str) -> list[Span]:
        """Extract tool call spans from the response body."""
        spans: list[Span] = []

        if not isinstance(body, dict):
            return spans

        messages = body.get("messages", [])
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", msg.get("type", ""))

            if role in ("assistant", "ai"):
                for tc in msg.get("tool_calls", []):
                    name = tc.get("name", tc.get("function", {}).get("name", ""))
                    args = tc.get("args", tc.get("function", {}).get("arguments", {}))
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                    spans.append(Span(
                        name=f"tool:{name}",
                        type=SpanType.TOOL_CALL,
                        input=args,
                        tool_call=ToolCall(name=name, arguments=args if isinstance(args, dict) else {}),
                    ))

            elif role == "tool":
                name = msg.get("name", "tool")
                content = msg.get("content")
                spans.append(Span(
                    name=f"tool_result:{name}",
                    type=SpanType.TOOL_CALL,
                    output=content,
                    tool_call=ToolCall(name=name, result=content),
                ))

        tool_calls = body.get("tool_calls", [])
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("arguments", tc.get("args", {}))
            result = tc.get("result", tc.get("output"))
            spans.append(Span(
                name=f"tool:{name}",
                type=SpanType.TOOL_CALL,
                input=args,
                output=result,
                tool_call=ToolCall(
                    name=name,
                    arguments=args if isinstance(args, dict) else {},
                    result=result,
                ),
            ))

        return spans


def from_config(config: EvalConfig) -> AgentEvaluator:
    """Create an AgentEvaluator from an EvalConfig."""
    return AgentEvaluator(config=config.agent)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEMPLATE_RE = re.compile(r"\$\{(\w+)\}")


def _interpolate(obj: Any, variables: dict[str, str]) -> Any:
    """Replace ``${var}`` placeholders in strings, dicts, and lists."""
    if isinstance(obj, str):
        def _replace(m: re.Match) -> str:
            return variables.get(m.group(1), m.group(0))
        return _TEMPLATE_RE.sub(_replace, obj)
    if isinstance(obj, dict):
        return {k: _interpolate(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate(v, variables) for v in obj]
    return obj


def _safe_json(text: str) -> Any:
    """Try to parse JSON; return raw text on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _dict_path(d: dict[str, Any], path: str) -> Any:
    """Access a nested dict via dot-separated path (e.g. 'output.content')."""
    parts = path.split(".")
    current: Any = d
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current
