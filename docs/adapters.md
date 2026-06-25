# Framework Adapters

agentic-eval provides adapters to import traces from popular agent frameworks. Each adapter converts framework-specific data into agentic-eval's `Trace` format, so you can evaluate agents regardless of how they were built.

## Google Gemini

Works with both the `google-genai` (new unified SDK) and `google-generativeai` (older SDK).

```python
from agentic_eval.adapters import from_gemini
from agentic_eval import run_evaluation

# From chat history (list of content dicts)
trace = from_gemini(chat.history, model="gemini-2.0-flash")

# From a GenerateContentResponse object
trace = from_gemini(response=gemini_response)

# Both together (avoids double-counting the last model turn)
trace = from_gemini(chat.history, response=gemini_response, model="gemini-2.0-flash")

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

**Supported features:**
- Multi-part responses (text + function calls)
- `functionCall` / `functionResponse` parts (both camelCase and snake_case)
- SDK Content objects (auto-converted to dicts)
- Token usage metadata extraction
- Model name tracking

## LangChain / LangGraph

Converts LangSmith run dicts or LangChain callback data.

```python
from agentic_eval.adapters import from_langchain

# From a LangSmith run dict
trace = from_langchain(langsmith_run_dict)

result = run_evaluation(trace, skill="./SKILL.md")
```

**Expected input format:**
```python
{
    "id": "run-id",
    "inputs": {"query": "..."},
    "outputs": {"result": "..."},
    "run_type": "chain",  # chain, llm, tool, retriever, agent
    "start_time": "2024-01-15T10:00:00Z",
    "end_time": "2024-01-15T10:00:05Z",
    "child_runs": [...]  # Nested runs become child spans
}
```

## OpenAI Agents SDK

Converts OpenAI ChatCompletion message lists and tool call responses.

```python
from agentic_eval.adapters import from_openai

# From conversation messages
trace = from_openai(messages=conversation)

# With a ChatCompletion response
trace = from_openai(messages=conversation, response=api_response)

result = run_evaluation(trace, skill="./SKILL.md")
```

**Handles:**
- Assistant messages with `tool_calls`
- Tool result messages
- Function call messages (legacy format)
- JSON string arguments (auto-parsed)

## Langfuse

Converts Langfuse observations into hierarchical traces. Supports both the v2 observation-list format (from `api.observations.get_many()`) and legacy trace dicts (from `GET /api/public/traces/{traceId}`).

```python
from agentic_eval.adapters import from_langfuse
from agentic_eval import run_evaluation

# From a list of observation dicts (v2 API / SDK)
observations = langfuse.api.observations.get_many(
    trace_id="your-trace-id",
    fields="core,basic,io,usage,model",
)
trace = from_langfuse(observations.data)

# From a legacy trace dict
trace_data = langfuse.fetch_trace("trace-id")
trace = from_langfuse(trace_data)

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

**Observation type mapping:**

| Langfuse type | agentic-eval type |
|---|---|
| `GENERATION` | `LLM_CALL` |
| `SPAN` | `AGENT_STEP` |
| `EVENT` | `CUSTOM` |
| `TOOL` | `TOOL_CALL` |

Names containing "retriev", "search", "rag", or "vector" are inferred as `RETRIEVAL`. Token usage and model metadata are automatically extracted.

**Handles:**
- Both camelCase (`parentObservationId`) and snake_case (`parent_observation_id`) keys
- SDK objects with `model_dump()` (auto-converted to dicts)
- Error-level observations (extracted from `level` field)
- Nested parent-child hierarchies via `parentObservationId`

## MLflow

Converts MLflow traces and spans into agentic-eval format. Accepts MLflow `Trace` objects, serialised trace dicts, or plain span lists.

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

**Span type mapping:**

| MLflow SpanType | agentic-eval type |
|---|---|
| `TOOL` | `TOOL_CALL` |
| `RETRIEVER` | `RETRIEVAL` |
| `LLM`, `CHAT_MODEL`, `EMBEDDING` | `LLM_CALL` |
| `AGENT`, `CHAIN`, `WORKFLOW`, `TASK` | `AGENT_STEP` |
| `PARSER`, `RERANKER`, `MEMORY`, `GUARDRAIL`, `EVALUATOR` | `CUSTOM` |

**Handles:**
- All 15 predefined MLflow SpanTypes plus custom strings
- `RETRIEVER` spans with document list outputs
- Error detection from both `status.status_code` and exception events
- Span attributes and model metadata extraction
- Nanosecond timestamps (OpenTelemetry-compatible)
- SDK Span objects with `to_dict()` / `model_dump()`

## OpenTelemetry

Converts OTel span exports (JSON format) into hierarchical traces.

```python
from agentic_eval.adapters import from_otel

# From exported OTel spans
trace = from_otel(exported_spans)

# With a custom trace ID
trace = from_otel(exported_spans, trace_id="custom-id")

result = run_evaluation(trace, skill="./SKILL.md")
```

**Span type inference:**
- `tool.name` attribute → `TOOL_CALL`
- `gen_ai.system` or `llm.system` attribute → `LLM_CALL`
- "retriev" or "search" in name → `RETRIEVAL`
- "agent" or "chain" in name → `AGENT_STEP`

**Supported attributes:** `input`, `output`, `gen_ai.prompt`, `gen_ai.completion`, `tool.name`, `tool.parameters`, `tool.result`

## Writing a Custom Adapter

If your framework isn't covered, create your own adapter:

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
