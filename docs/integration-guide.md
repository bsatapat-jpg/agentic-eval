# Integration Guide

This guide shows how to integrate agentic-eval into your agent project, regardless of your architecture.

## Overview

There are **four integration patterns** depending on your setup:

| Pattern | When to use | Effort |
|---|---|---|
| [Config-driven (YAML)](#1-config-driven-yaml) | CI/CD pipelines, standardised evaluation | 5 min |
| [Adapter import](#2-adapter-import) | You already have traces in Langfuse/MLflow/OTel | 5 min |
| [Decorator wrap](#3-decorator-wrap) | You own the agent code and want inline evaluation | 10 min |
| [HTTP live evaluation](#4-http-live-evaluation) | Agent runs behind an API, no code changes | 10 min |

---

## 1. Config-Driven (YAML)

Create an `agentic-eval.yaml` at your project root. This is the recommended approach for CI/CD.

```yaml
project: my-agent

skills:
  - path: ./skills/search/SKILL.md
    thresholds:
      task_completion: 0.9
      groundedness: 0.8
  - path: ./skills/summarise/SKILL.md
    thresholds:
      task_completion: 1.0

metrics:
  enabled:
    - task_completion
    - groundedness
    - hallucination
    - tool_response_alignment
  weights:
    task_completion: 0.25
    groundedness: 0.25
    hallucination: 0.25
    tool_response_alignment: 0.25
  use_llm_judge: false

agent:
  url: http://localhost:8000/api/chat
  method: POST
  headers:
    Authorization: "Bearer ${AUTH_TOKEN}"
    Content-Type: application/json
  body_template:
    messages:
      - role: user
        content: "${query}"
  timeout: 30
  response_path: output.content

test_cases:
  - input: "What is the status of Project Alpha?"
    expected_output: "on track"
    expected_tools: ["rag_search"]
  - input: "Show me Q3 pipeline numbers"
    expected_tools: ["salesforce_query"]
  - input: "Summarise the latest security advisory"
    skill: ./skills/summarise/SKILL.md

ci:
  fail_below: 0.7
  fail_on_any_metric_below: 0.4
  save: true
  db_path: ./eval_results.db
  output_file: ./eval_report.json
```

Then run:

```bash
agentic-eval ci                        # auto-finds agentic-eval.yaml
agentic-eval ci --config ./custom.yaml  # explicit path
agentic-eval ci --fail-below 0.8       # override threshold
agentic-eval ci --format json          # JSON output for CI parsing
```

### Environment Variable Interpolation

Use `${VAR_NAME}` in any string value — headers, URLs, body templates:

```yaml
agent:
  url: "${AGENT_BASE_URL}/api/chat"
  headers:
    Authorization: "Bearer ${API_TOKEN}"
```

### Config Schema Reference

| Key | Type | Description |
|---|---|---|
| `project` | string | Project name (for display/reports) |
| `skills[].path` | string | Path to SKILL.md file |
| `skills[].thresholds` | dict | Per-metric pass thresholds |
| `skills[].weights` | dict | Per-metric score weights |
| `metrics.enabled` | list | Metric names to run (null = all) |
| `metrics.weights` | dict | Global metric weights |
| `metrics.use_llm_judge` | bool | Enable LLM-as-judge mode |
| `agent.url` | string | Agent endpoint URL |
| `agent.method` | string | HTTP method (default: POST) |
| `agent.headers` | dict | Request headers |
| `agent.body_template` | dict | Request body with `${query}` placeholder |
| `agent.timeout` | float | Request timeout in seconds |
| `agent.response_path` | string | Dot-path to extract output (e.g. `result.text`) |
| `test_cases[].input` | string | Test query |
| `test_cases[].expected_output` | string | Expected response (optional) |
| `test_cases[].expected_tools` | list | Expected tool names (optional) |
| `test_cases[].skill` | string | Override skill for this test case |
| `ci.fail_below` | float | Fail if overall score is below this |
| `ci.fail_on_any_metric_below` | float | Fail if any single metric is below this |
| `ci.save` | bool | Persist results to SQLite |
| `ci.db_path` | string | Database file path |
| `ci.output_file` | string | Write JSON report to this file |

---

## 2. Adapter Import

If your agent already produces traces in an observability platform, import them directly.

### From Langfuse

```python
from langfuse import get_client
from agentic_eval.adapters import from_langfuse
from agentic_eval import run_evaluation

langfuse = get_client()
observations = langfuse.api.observations.get_many(
    trace_id="your-trace-id",
    fields="core,basic,io,usage,model",
)
trace = from_langfuse(observations.data)

result = run_evaluation(trace, skill="./skills/SKILL.md")
result.print()
```

### From MLflow

```python
import mlflow
from agentic_eval.adapters import from_mlflow
from agentic_eval import run_evaluation

mlflow_trace = mlflow.get_trace("<trace_id>")
trace = from_mlflow(mlflow_trace)

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

### From LangGraph State

```python
from agentic_eval.adapters import from_langgraph
from agentic_eval import run_evaluation

# After running a LangGraph agent
final_state = await graph.ainvoke({"messages": [HumanMessage("query")]})
trace = from_langgraph(final_state)

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

### From LangGraph Streaming Events

```python
from agentic_eval.adapters import from_langgraph

events = []
async for event in graph.astream_events(input_data, version="v2"):
    events.append(event)

trace = from_langgraph(events)
result = run_evaluation(trace, skill="./SKILL.md")
```

### From OpenTelemetry Spans

```python
from agentic_eval.adapters import from_otel

trace = from_otel(exported_spans)
result = run_evaluation(trace, skill="./SKILL.md")
```

### From Gemini API

```python
from agentic_eval.adapters import from_gemini

trace = from_gemini(chat.history, model="gemini-2.0-flash")
result = run_evaluation(trace, skill="./SKILL.md")
```

---

## 3. Decorator Wrap

If you own the agent code, wrap your agent function for automatic trace capture.

### Simple Agent

```python
from agentic_eval import evaluate, record_tool_call

@evaluate(skill="./SKILL.md", auto_save=True)
def my_agent(query: str) -> str:
    record_tool_call("search", arguments={"q": query}, result="found it")
    return "Done!"

result = my_agent("find the bug")
my_agent.last_eval.print()
```

### LangChain Agent

```python
from agentic_eval import evaluate, record_tool_call, record_llm_call

@evaluate(skill="./SKILL.md", auto_save=True)
def langchain_agent(query: str) -> str:
    # Your LangChain code here
    chain = prompt | llm | output_parser
    
    record_llm_call(input=query, output="...", model="gpt-4")
    record_tool_call("retriever", arguments={"query": query}, result="docs...")
    
    return chain.invoke({"query": query})
```

### Async Agent (FastAPI, LangGraph, etc.)

```python
from agentic_eval import evaluate

@evaluate(skill="./SKILL.md", auto_save=True)
async def async_agent(query: str) -> str:
    result = await llm.ainvoke(query)
    return result
```

### With Callbacks for CI/CD

```python
def on_eval_done(result):
    if result.verdict.value == "fail":
        notify_slack(f"FAILED: {result.overall_score:.1%}")
    # Send to your metrics pipeline
    datadog.gauge("agent.eval_score", result.overall_score)

@evaluate(
    skill="./SKILL.md",
    auto_save=True,
    on_complete=on_eval_done,
    thresholds={"task_completion": 1.0, "groundedness": 0.8},
)
def my_agent(query: str) -> str:
    ...
```

---

## 4. HTTP Live Evaluation

Evaluate a running agent without modifying its code — just point to its API.

### Python API

```python
from agentic_eval import AgentEvaluator

evaluator = AgentEvaluator(
    url="http://localhost:8000/api/chat",
    headers={"Authorization": "Bearer <token>"},
    body_template={
        "messages": [{"role": "user", "content": "${query}"}],
    },
    response_path="output.content",
)

results = evaluator.evaluate(
    test_cases=[
        {"input": "What is the status?", "expected_tools": ["rag_search"]},
        {"input": "Show pipeline", "expected_output": "Q3 pipeline"},
    ],
    skill="./SKILL.md",
    thresholds={"task_completion": 0.9},
)

for r in results:
    r.print()
```

### LangGraph Streaming API

```python
evaluator = AgentEvaluator(
    url="http://localhost:2026/threads/{thread_id}/runs",
    method="POST",
    headers={"Authorization": "Bearer ${AUTH_TOKEN}"},
    body_template={
        "assistant_id": "my_assistant",
        "input": {
            "messages": [{"role": "user", "content": "${query}"}],
        },
    },
)
```

### From Config

```python
from agentic_eval import load_config
from agentic_eval.agent_evaluator import from_config

config = load_config("./agentic-eval.yaml")
evaluator = from_config(config)

results = evaluator.evaluate(
    test_cases=config.test_cases,
    skill=config.skills[0].path if config.skills else None,
)
```

---

## Architecture-Specific Examples

### Aegra / LangGraph Platform

```yaml
# agentic-eval.yaml
project: sales-assistant-v2

agent:
  url: http://localhost:2026/sales-assistant/threads/{thread_id}/runs
  method: POST
  headers:
    Authorization: "Bearer ${SSO_TOKEN}"
  body_template:
    assistant_id: sales_assistant_v2
    input:
      messages:
        - role: user
          content: "${query}"
    stream_mode: ["values"]

skills:
  - path: ./skills/salesforce-query/SKILL.md
    thresholds:
      task_completion: 0.9
      tool_response_alignment: 0.7

test_cases:
  - input: "What deals closed this quarter?"
    expected_tools: ["salesforce_query"]
  - input: "Tell me about OpenShift pricing"
    expected_tools: ["rag_search"]
```

### CrewAI

```python
from crewai import Crew, Agent, Task
from agentic_eval import evaluate, record_tool_call

@evaluate(skill="./SKILL.md", auto_save=True)
def run_crew(query: str) -> str:
    crew = Crew(agents=[...], tasks=[...])
    result = crew.kickoff(inputs={"query": query})
    return str(result)
```

### AutoGen

```python
from autogen import AssistantAgent, UserProxyAgent
from agentic_eval import trace_context, record_tool_call, run_evaluation

with trace_context(input=query) as trace:
    assistant = AssistantAgent("assistant", llm_config={...})
    user_proxy = UserProxyAgent("user", ...)
    user_proxy.initiate_chat(assistant, message=query)
    trace.output = assistant.last_message()["content"]

result = run_evaluation(trace, skill="./SKILL.md")
```

### Custom Agent Loop

```python
from agentic_eval import trace_context, record_tool_call, record_llm_call, run_evaluation

with trace_context(input=query) as trace:
    messages = [{"role": "user", "content": query}]
    
    while True:
        response = llm.chat(messages)
        record_llm_call(input=messages, output=response.content, model="gpt-4o")
        
        if response.tool_calls:
            for tc in response.tool_calls:
                result = execute_tool(tc.name, tc.args)
                record_tool_call(tc.name, arguments=tc.args, result=result)
                messages.append({"role": "tool", "content": result})
        else:
            trace.output = response.content
            break

result = run_evaluation(trace, skill="./SKILL.md")
```

---

## CI/CD Integration

### GitHub Actions

```yaml
name: Agent Evaluation
on: [push, pull_request]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Start agent
        run: docker compose up -d
      
      - name: Wait for agent
        run: sleep 10
      
      - name: Install agentic-eval
        run: pip install agentic-eval
      
      - name: Run evaluation
        env:
          AUTH_TOKEN: ${{ secrets.AUTH_TOKEN }}
        run: agentic-eval ci --format json
      
      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-results
          path: eval_report.json
```

### GitLab CI

```yaml
evaluate:
  stage: test
  script:
    - pip install agentic-eval
    - agentic-eval ci --config ./agentic-eval.yaml --format json
  artifacts:
    paths:
      - eval_report.json
    when: always
  variables:
    AUTH_TOKEN: $AUTH_TOKEN
```

### pytest Integration

```python
# tests/test_agent_skills.py
from agentic_eval import assert_skill

def test_search_skill():
    result = my_agent("find the bug in auth.py")
    assert_skill(
        actual=result,
        skill="./skills/search/SKILL.md",
        thresholds={
            "task_completion": 1.0,
            "tool_selection": 0.8,
            "groundedness": 0.7,
        },
    )

def test_no_hallucination():
    result = my_agent("what is our SLA?")
    assert_skill(
        actual=result,
        skill="./skills/policy/SKILL.md",
        thresholds={"hallucination": 0.9},
    )
```

---

## Migration from Existing Evaluation

### If you use an external eval pipeline

Replace or augment it:

```bash
# Before
curl -X POST $EVAL_PIPELINE_URL -d '{"agent_url": "...", "dataset": "..."}'

# After (in addition to or replacing the above)
agentic-eval ci
```

### If you use DeepEval

agentic-eval is complementary — it evaluates the *trajectory*, not just output:

```python
# DeepEval: output-only evaluation
from deepeval.metrics import GEval

# agentic-eval: trajectory evaluation (tool calls, steps, grounding)
from agentic_eval import run_evaluation
result = run_evaluation(trace, skill="./SKILL.md")
```

### If you use LangSmith

Import your existing LangSmith traces:

```python
from langsmith import Client
from agentic_eval.adapters import from_langchain
from agentic_eval import run_evaluation

client = Client()
runs = client.list_runs(project_name="my-project")

for run in runs:
    trace = from_langchain(run.dict())
    result = run_evaluation(trace, skill="./SKILL.md")
```
