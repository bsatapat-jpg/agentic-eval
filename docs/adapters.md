# Framework Adapters

> Import traces from **any** agent framework — no code changes required.

Each adapter converts framework-specific data into agentic-eval's `Trace` format, so you can evaluate agents regardless of how they were built.

```
 ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌──────┐
 │ LangGraph │ │ Langfuse  │ │  MLflow  │ │ Gemini │ │LangChain │ │ OpenAI │ │ OTel │
 └─────┬─────┘ └─────┬─────┘ └────┬─────┘ └───┬────┘ └────┬─────┘ └───┬────┘ └──┬───┘
       └──────────────┴────────────┴───────────┴───────────┴───────────┴─────────┘
                                           │
                                    ┌──────▼──────┐
                                    │ agentic-eval │
                                    │    Trace     │
                                    └─────────────┘
```

| Adapter | Source | Input format |
|:---|:---|:---|
| [`from_langgraph`](#langgraph) | LangGraph / Aegra | State dict, message list, streaming events |
| [`from_langfuse`](#langfuse) | Langfuse | Observations API v2 or legacy trace dict |
| [`from_mlflow`](#mlflow) | MLflow | Trace object, serialised dict, or span list |
| [`from_gemini`](#google-gemini) | Google Gemini | Chat history, GenerateContentResponse |
| [`from_langchain`](#langchain--langsmith) | LangChain / LangSmith | Run dicts with child_runs |
| [`from_openai`](#openai-agents-sdk) | OpenAI | ChatCompletion messages + tool calls |
| [`from_otel`](#opentelemetry) | OpenTelemetry | Exported OTel spans (JSON) |

<br>

---

## LangGraph

> Recommended for **LangGraph** and **Aegra**-based agents.

Converts LangGraph agent state, message lists, or streaming events.

```python
from agentic_eval.adapters import from_langgraph
from agentic_eval import run_evaluation

# From LangGraph state (most common)
final_state = await graph.ainvoke({"messages": [HumanMessage("query")]})
trace = from_langgraph(final_state)

# From a message list directly
trace = from_langgraph(messages)

# From astream_events (streaming)
events = [e async for e in graph.astream_events(input, version="v2")]
trace = from_langgraph(events)

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

<details>
<summary><strong>Type mappings</strong></summary>

**Messages:**

| LangChain type | agentic-eval type |
|:---|:---|
| `AIMessage` / `ai` | `LLM_CALL` (with child `TOOL_CALL` spans) |
| `ToolMessage` / `tool` | `TOOL_CALL` (with result) |
| `HumanMessage` / `human` | Extracted as trace input |

**Streaming events:**

| Event | agentic-eval type |
|:---|:---|
| `on_chat_model_end` | `LLM_CALL` |
| `on_tool_start` / `on_tool_end` | `TOOL_CALL` |
| `on_retriever_end` | `RETRIEVAL` |

</details>

<br>

---

## Langfuse

Supports both the **v2 observation-list** format and **legacy trace dicts**.

```python
from agentic_eval.adapters import from_langfuse
from agentic_eval import run_evaluation

# v2 API (recommended)
observations = langfuse.api.observations.get_many(
    trace_id="your-trace-id",
    fields="core,basic,io,usage,model",
)
trace = from_langfuse(observations.data)

# Legacy trace dict
trace_data = langfuse.fetch_trace("trace-id")
trace = from_langfuse(trace_data)

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

<details>
<summary><strong>Type mappings & features</strong></summary>

| Langfuse type | agentic-eval type |
|:---|:---|
| `GENERATION` | `LLM_CALL` |
| `SPAN` | `AGENT_STEP` |
| `EVENT` | `CUSTOM` |
| `TOOL` | `TOOL_CALL` |

Names containing "retriev", "search", "rag", or "vector" are inferred as `RETRIEVAL`.

**Also handles:** camelCase & snake_case keys, SDK objects with `model_dump()`, error-level observations, token usage & model metadata.

</details>

<br>

---

## MLflow

Accepts MLflow `Trace` objects, serialised trace dicts, or plain span lists.

```python
from agentic_eval.adapters import from_mlflow
from agentic_eval import run_evaluation
import mlflow

# From an MLflow Trace object
mlflow_trace = mlflow.get_trace("<trace_id>")
trace = from_mlflow(mlflow_trace)

# From a serialised trace dict
trace = from_mlflow({"info": trace_info, "data": {"spans": span_list}})

# From a plain list of span dicts
trace = from_mlflow(span_dicts)

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

<details>
<summary><strong>Type mappings (all 15 MLflow SpanTypes)</strong></summary>

| MLflow SpanType | agentic-eval type |
|:---|:---|
| `TOOL` | `TOOL_CALL` |
| `RETRIEVER` | `RETRIEVAL` |
| `LLM`, `CHAT_MODEL`, `EMBEDDING` | `LLM_CALL` |
| `AGENT`, `CHAIN`, `WORKFLOW`, `TASK` | `AGENT_STEP` |
| `PARSER`, `RERANKER`, `MEMORY`, `GUARDRAIL`, `EVALUATOR` | `CUSTOM` |

**Also handles:** `RETRIEVER` spans with document list outputs, error detection from `status.status_code` and exception events, nanosecond timestamps, SDK Span objects.

</details>

<br>

---

## Google Gemini

Works with both `google-genai` (new unified SDK) and `google-generativeai` (older SDK).

```python
from agentic_eval.adapters import from_gemini
from agentic_eval import run_evaluation

# From chat history
trace = from_gemini(chat.history, model="gemini-2.0-flash")

# From a GenerateContentResponse
trace = from_gemini(response=gemini_response)

# Both (avoids double-counting the last model turn)
trace = from_gemini(chat.history, response=gemini_response, model="gemini-2.0-flash")

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

**Handles:** Multi-part responses, `functionCall`/`functionResponse` parts (camelCase & snake_case), SDK Content objects, token usage metadata, model name tracking.

<br>

---

## LangChain / LangSmith

Converts LangSmith run dicts or LangChain callback data.

```python
from agentic_eval.adapters import from_langchain

trace = from_langchain(langsmith_run_dict)
result = run_evaluation(trace, skill="./SKILL.md")
```

<details>
<summary><strong>Expected input format</strong></summary>

```python
{
    "id": "run-id",
    "inputs": {"query": "..."},
    "outputs": {"result": "..."},
    "run_type": "chain",   # chain, llm, tool, retriever, agent
    "start_time": "2024-01-15T10:00:00Z",
    "end_time": "2024-01-15T10:00:05Z",
    "child_runs": [...]    # Nested runs become child spans
}
```

</details>

<br>

---

## OpenAI Agents SDK

Converts OpenAI ChatCompletion message lists and tool call responses.

```python
from agentic_eval.adapters import from_openai

trace = from_openai(messages=conversation)
trace = from_openai(messages=conversation, response=api_response)
result = run_evaluation(trace, skill="./SKILL.md")
```

**Handles:** Assistant messages with `tool_calls`, tool result messages, function call messages (legacy format), JSON string arguments (auto-parsed).

<br>

---

## OpenTelemetry

Converts OTel span exports (JSON format) into hierarchical traces.

```python
from agentic_eval.adapters import from_otel

trace = from_otel(exported_spans)
trace = from_otel(exported_spans, trace_id="custom-id")
result = run_evaluation(trace, skill="./SKILL.md")
```

<details>
<summary><strong>Span type inference rules</strong></summary>

| Signal | Inferred type |
|:---|:---|
| `tool.name` attribute | `TOOL_CALL` |
| `gen_ai.system` or `llm.system` attribute | `LLM_CALL` |
| "retriev" or "search" in name | `RETRIEVAL` |
| "agent" or "chain" in name | `AGENT_STEP` |

**Supported attributes:** `input`, `output`, `gen_ai.prompt`, `gen_ai.completion`, `tool.name`, `tool.parameters`, `tool.result`

</details>

<br>

---

## Writing a Custom Adapter

If your framework isn't covered, create your own:

```python
from agentic_eval.models import Trace, Span, SpanType, ToolCall
from datetime import datetime, timezone

def from_my_framework(data: dict) -> Trace:
    trace = Trace(
        input=data.get("query"),
        output=data.get("result"),
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )

    for step in data.get("steps", []):
        span = Span(
            name=step["name"],
            type=SpanType.TOOL_CALL,
            tool_call=ToolCall(
                name=step["tool"],
                arguments=step.get("args", {}),
                result=step.get("output"),
            ),
        )
        trace.spans.append(span)

    return trace
```

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="metrics.md">Metrics</a> · <a href="integration-guide.md">Integration Guide</a> · <a href="custom-metrics.md">Custom Metrics</a>
</p>
