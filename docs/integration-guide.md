# Integration Guide

> Get agentic-eval into your project in minutes — regardless of your architecture.

<br>

## Choose Your Pattern

| # | Pattern | When to use | Effort |
|:---:|:---|:---|:---:|
| 1 | [Config-driven (YAML)](#1-config-driven-yaml) | CI/CD pipelines, standardised evaluation | ~5 min |
| 2 | [Adapter import](#2-adapter-import) | You already have traces in Langfuse / MLflow / OTel | ~5 min |
| 3 | [Decorator wrap](#3-decorator-wrap) | You own the agent code and want inline evaluation | ~10 min |
| 4 | [HTTP live evaluation](#4-http-live-evaluation) | Agent runs behind an API, no code changes needed | ~10 min |

<br>

---

## 1. Config-Driven (YAML)

> Recommended for CI/CD. Zero Python required.

Create an `agentic-eval.yaml` at your project root:

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
  enabled: [task_completion, groundedness, hallucination, tool_response_alignment]
  weights:
    task_completion: 0.25
    groundedness: 0.25
    hallucination: 0.25
    tool_response_alignment: 0.25

agent:
  url: http://localhost:8000/api/chat
  method: POST
  headers:
    Authorization: "Bearer ${AUTH_TOKEN}"
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

ci:
  fail_below: 0.7
  fail_on_any_metric_below: 0.4
  save: true
  output_file: ./eval_report.json
```

Then run:

```bash
agentic-eval ci                         # auto-finds agentic-eval.yaml
agentic-eval ci --config ./custom.yaml  # explicit path
agentic-eval ci --fail-below 0.8        # override threshold
agentic-eval ci --format json           # machine-readable output
```

<details>
<summary><strong>Environment variable interpolation</strong></summary>

Use `${VAR_NAME}` in any string value:

```yaml
agent:
  url: "${AGENT_BASE_URL}/api/chat"
  headers:
    Authorization: "Bearer ${API_TOKEN}"
```

</details>

<details>
<summary><strong>Full config schema reference</strong></summary>

| Key | Type | Description |
|:---|:---|:---|
| `project` | string | Project name (for display / reports) |
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

</details>

<br>

---

## 2. Adapter Import

> Already have traces? Import them directly.

<details>
<summary><strong>From Langfuse</strong></summary>

```python
from langfuse import get_client
from agentic_eval.adapters import from_langfuse
from agentic_eval import run_evaluation

langfuse = get_client()
observations = langfuse.api.observations.get_many(
    trace_id="your-trace-id", fields="core,basic,io,usage,model",
)
trace = from_langfuse(observations.data)
result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

</details>

<details>
<summary><strong>From MLflow</strong></summary>

```python
import mlflow
from agentic_eval.adapters import from_mlflow
from agentic_eval import run_evaluation

mlflow_trace = mlflow.get_trace("<trace_id>")
trace = from_mlflow(mlflow_trace)
result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

</details>

<details>
<summary><strong>From LangGraph state</strong></summary>

```python
from agentic_eval.adapters import from_langgraph
from agentic_eval import run_evaluation

final_state = await graph.ainvoke({"messages": [HumanMessage("query")]})
trace = from_langgraph(final_state)
result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

</details>

<details>
<summary><strong>From LangGraph streaming events</strong></summary>

```python
from agentic_eval.adapters import from_langgraph

events = [e async for e in graph.astream_events(input_data, version="v2")]
trace = from_langgraph(events)
result = run_evaluation(trace, skill="./SKILL.md")
```

</details>

<details>
<summary><strong>From OpenTelemetry / Gemini / OpenAI</strong></summary>

```python
from agentic_eval.adapters import from_otel, from_gemini, from_openai

trace = from_otel(exported_spans)
trace = from_gemini(chat.history, model="gemini-2.0-flash")
trace = from_openai(messages=conversation)
```

</details>

<br>

---

## 3. Decorator Wrap

> Own the code? Wrap it.

<details>
<summary><strong>Simple agent</strong></summary>

```python
from agentic_eval import evaluate, record_tool_call

@evaluate(skill="./SKILL.md", auto_save=True)
def my_agent(query: str) -> str:
    record_tool_call("search", arguments={"q": query}, result="found it")
    return "Done!"

result = my_agent("find the bug")
my_agent.last_eval.print()
```

</details>

<details>
<summary><strong>LangChain agent</strong></summary>

```python
from agentic_eval import evaluate, record_tool_call, record_llm_call

@evaluate(skill="./SKILL.md", auto_save=True)
def langchain_agent(query: str) -> str:
    chain = prompt | llm | output_parser
    record_llm_call(input=query, output="...", model="gpt-4")
    record_tool_call("retriever", arguments={"query": query}, result="docs...")
    return chain.invoke({"query": query})
```

</details>

<details>
<summary><strong>Async agent (FastAPI, LangGraph, etc.)</strong></summary>

```python
from agentic_eval import evaluate

@evaluate(skill="./SKILL.md", auto_save=True)
async def async_agent(query: str) -> str:
    result = await llm.ainvoke(query)
    return result
```

</details>

<details>
<summary><strong>With callbacks for CI/CD</strong></summary>

```python
def on_eval_done(result):
    if result.verdict.value == "fail":
        notify_slack(f"FAILED: {result.overall_score:.1%}")
    datadog.gauge("agent.eval_score", result.overall_score)

@evaluate(
    skill="./SKILL.md", auto_save=True,
    on_complete=on_eval_done,
    thresholds={"task_completion": 1.0, "groundedness": 0.8},
)
def my_agent(query: str) -> str:
    ...
```

</details>

<br>

---

## 4. HTTP Live Evaluation

> No code changes. Just point to the API.

```python
from agentic_eval import AgentEvaluator

evaluator = AgentEvaluator(
    url="http://localhost:8000/api/chat",
    headers={"Authorization": "Bearer <token>"},
    body_template={"messages": [{"role": "user", "content": "${query}"}]},
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

<details>
<summary><strong>LangGraph streaming API example</strong></summary>

```python
evaluator = AgentEvaluator(
    url="http://localhost:2026/threads/{thread_id}/runs",
    method="POST",
    headers={"Authorization": "Bearer ${AUTH_TOKEN}"},
    body_template={
        "assistant_id": "my_assistant",
        "input": {"messages": [{"role": "user", "content": "${query}"}]},
    },
)
```

</details>

<details>
<summary><strong>From YAML config</strong></summary>

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

</details>

<br>

---

## Architecture-Specific Examples

<details>
<summary><strong>Aegra / LangGraph Platform</strong></summary>

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
      messages: [{ role: user, content: "${query}" }]
skills:
  - path: ./skills/salesforce-query/SKILL.md
    thresholds: { task_completion: 0.9, tool_response_alignment: 0.7 }
test_cases:
  - input: "What deals closed this quarter?"
    expected_tools: ["salesforce_query"]
```

</details>

<details>
<summary><strong>CrewAI</strong></summary>

```python
from crewai import Crew
from agentic_eval import evaluate

@evaluate(skill="./SKILL.md", auto_save=True)
def run_crew(query: str) -> str:
    crew = Crew(agents=[...], tasks=[...])
    return str(crew.kickoff(inputs={"query": query}))
```

</details>

<details>
<summary><strong>AutoGen</strong></summary>

```python
from autogen import AssistantAgent, UserProxyAgent
from agentic_eval import trace_context, run_evaluation

with trace_context(input=query) as trace:
    assistant = AssistantAgent("assistant", llm_config={...})
    user_proxy = UserProxyAgent("user", ...)
    user_proxy.initiate_chat(assistant, message=query)
    trace.output = assistant.last_message()["content"]

result = run_evaluation(trace, skill="./SKILL.md")
```

</details>

<details>
<summary><strong>Custom agent loop</strong></summary>

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

</details>

<br>

---

## CI/CD Integration

<details>
<summary><strong>GitHub Actions</strong></summary>

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

</details>

<details>
<summary><strong>GitLab CI</strong></summary>

```yaml
evaluate:
  stage: test
  script:
    - pip install agentic-eval
    - agentic-eval ci --config ./agentic-eval.yaml --format json
  artifacts:
    paths: [eval_report.json]
    when: always
  variables:
    AUTH_TOKEN: $AUTH_TOKEN
```

</details>

<details>
<summary><strong>pytest</strong></summary>

```python
from agentic_eval import assert_skill

def test_search_skill():
    result = my_agent("find the bug in auth.py")
    assert_skill(
        actual=result, skill="./skills/search/SKILL.md",
        thresholds={"task_completion": 1.0, "tool_selection": 0.8, "groundedness": 0.7},
    )

def test_no_hallucination():
    result = my_agent("what is our SLA?")
    assert_skill(actual=result, skill="./skills/policy/SKILL.md",
                 thresholds={"hallucination": 0.9})
```

</details>

<br>

---

## Migration

<details>
<summary><strong>From an external eval pipeline</strong></summary>

```bash
# Before
curl -X POST $EVAL_PIPELINE_URL -d '{"agent_url": "...", "dataset": "..."}'

# After
agentic-eval ci
```

</details>

<details>
<summary><strong>From DeepEval</strong></summary>

agentic-eval is complementary — it evaluates the *trajectory*, not just output:

```python
# DeepEval: output-only
from deepeval.metrics import GEval

# agentic-eval: trajectory (tool calls, steps, grounding)
from agentic_eval import run_evaluation
result = run_evaluation(trace, skill="./SKILL.md")
```

</details>

<details>
<summary><strong>From LangSmith</strong></summary>

```python
from langsmith import Client
from agentic_eval.adapters import from_langchain
from agentic_eval import run_evaluation

client = Client()
for run in client.list_runs(project_name="my-project"):
    trace = from_langchain(run.dict())
    result = run_evaluation(trace, skill="./SKILL.md")
```

</details>

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="adapters.md">Adapters</a> · <a href="cli.md">CLI</a> · <a href="architecture.md">Architecture</a>
</p>
