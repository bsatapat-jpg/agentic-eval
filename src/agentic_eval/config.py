"""YAML-based project configuration for agentic-eval.

Create an ``agentic-eval.yaml`` (or ``.agentic-eval.yaml``) at your project
root to declare skills, thresholds, test cases, and CI settings.  Then run::

    agentic-eval ci                     # uses ./agentic-eval.yaml
    agentic-eval ci --config path.yaml  # explicit path

Example config::

    project: sales-assistant-v2

    skills:
      - path: ./skills/salesforce-query/SKILL.md
        thresholds:
          task_completion: 0.9
          groundedness: 0.8

    metrics:
      enabled:
        - task_completion
        - groundedness
        - hallucination
      weights:
        task_completion: 0.25
        groundedness: 0.25

    agent:
      url: http://localhost:2026/threads/{thread_id}/runs
      method: POST
      headers:
        Authorization: "Bearer ${AUTH_TOKEN}"
      body_template:
        assistant_id: sales_assistant_v2
        input:
          messages:
            - role: user
              content: "${query}"

    test_cases:
      - input: "What is the status of Project Alpha?"
        expected_output: "Project Alpha is on track"
        expected_tools: ["rag_search"]
      - input: "Show me Q3 pipeline"
        expected_tools: ["salesforce_query"]

    ci:
      fail_below: 0.7
      fail_on_any_metric_below: 0.4
      save: true
      db_path: ./eval_results.db
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


@dataclass
class SkillConfig:
    path: str
    thresholds: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)


@dataclass
class AgentConfig:
    url: str = ""
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body_template: dict[str, Any] = field(default_factory=dict)
    timeout: float = 60.0
    response_path: str = ""


@dataclass
class TestCase:
    input: str = ""
    expected_output: str | None = None
    expected_tools: list[str] = field(default_factory=list)
    skill: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class CIConfig:
    fail_below: float = 0.0
    fail_on_any_metric_below: float = 0.0
    save: bool = True
    db_path: str = "./agentic_eval_results.db"
    output_format: str = "table"
    output_file: str | None = None


@dataclass
class MetricsConfig:
    enabled: list[str] | None = None
    weights: dict[str, float] = field(default_factory=dict)
    use_llm_judge: bool = False


@dataclass
class EvalConfig:
    """Top-level evaluation configuration parsed from YAML."""
    project: str = ""
    skills: list[SkillConfig] = field(default_factory=list)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    test_cases: list[TestCase] = field(default_factory=list)
    ci: CIConfig = field(default_factory=CIConfig)

    @property
    def has_agent(self) -> bool:
        return bool(self.agent.url)

    @property
    def has_test_cases(self) -> bool:
        return len(self.test_cases) > 0


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _expand_env(value: str) -> str:
    """Replace ``${VAR}`` placeholders with environment variable values."""
    def _replace(match: re.Match) -> str:
        var = match.group(1)
        return os.environ.get(var, match.group(0))
    return _ENV_VAR_RE.sub(_replace, value)


def _expand_env_recursive(obj: Any) -> Any:
    """Walk a dict/list structure and expand env vars in all strings."""
    if isinstance(obj, str):
        return _expand_env(obj)
    if isinstance(obj, dict):
        return {k: _expand_env_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_recursive(v) for v in obj]
    return obj


def load_config(path: str | Path | None = None) -> EvalConfig:
    """Load evaluation configuration from a YAML file.

    If *path* is ``None``, searches for ``agentic-eval.yaml`` or
    ``.agentic-eval.yaml`` in the current directory and parents.

    Args:
        path: Explicit path to the YAML config file.

    Returns:
        Parsed ``EvalConfig``.

    Raises:
        FileNotFoundError: No config file found.
        ImportError: PyYAML is not installed.
    """
    if yaml is None:
        raise ImportError(
            "PyYAML is required for config file support. "
            "Install it: pip install pyyaml"
        )

    if path is not None:
        config_path = Path(path)
    else:
        config_path = _find_config()

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    raw = _expand_env_recursive(raw)

    return _parse_config(raw)


def _find_config() -> Path:
    """Search current directory and parents for a config file."""
    names = ["agentic-eval.yaml", "agentic-eval.yml", ".agentic-eval.yaml", ".agentic-eval.yml"]
    cwd = Path.cwd()

    for directory in [cwd, *cwd.parents]:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return candidate

    raise FileNotFoundError(
        "No agentic-eval.yaml found. Create one or specify --config. "
        "See docs/integration-guide.md for examples."
    )


def _parse_config(raw: dict[str, Any]) -> EvalConfig:
    """Parse raw YAML dict into typed config objects."""
    skills = [
        SkillConfig(
            path=s.get("path", ""),
            thresholds=s.get("thresholds", {}),
            weights=s.get("weights", {}),
        )
        for s in raw.get("skills", [])
    ]

    metrics_raw = raw.get("metrics", {})
    metrics = MetricsConfig(
        enabled=metrics_raw.get("enabled"),
        weights=metrics_raw.get("weights", {}),
        use_llm_judge=metrics_raw.get("use_llm_judge", False),
    )

    agent_raw = raw.get("agent", {})
    agent = AgentConfig(
        url=agent_raw.get("url", ""),
        method=agent_raw.get("method", "POST"),
        headers=agent_raw.get("headers", {}),
        body_template=agent_raw.get("body_template", {}),
        timeout=agent_raw.get("timeout", 60.0),
        response_path=agent_raw.get("response_path", ""),
    )

    test_cases = [
        TestCase(
            input=tc.get("input", ""),
            expected_output=tc.get("expected_output"),
            expected_tools=tc.get("expected_tools", []),
            skill=tc.get("skill"),
            tags=tc.get("tags", []),
        )
        for tc in raw.get("test_cases", [])
    ]

    ci_raw = raw.get("ci", {})
    ci = CIConfig(
        fail_below=ci_raw.get("fail_below", 0.0),
        fail_on_any_metric_below=ci_raw.get("fail_on_any_metric_below", 0.0),
        save=ci_raw.get("save", True),
        db_path=ci_raw.get("db_path", "./agentic_eval_results.db"),
        output_format=ci_raw.get("output_format", "table"),
        output_file=ci_raw.get("output_file"),
    )

    return EvalConfig(
        project=raw.get("project", ""),
        skills=skills,
        metrics=metrics,
        agent=agent,
        test_cases=test_cases,
        ci=ci,
    )
