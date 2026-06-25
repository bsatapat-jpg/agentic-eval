"""Framework adapters for importing traces from popular agent frameworks.

Adapters convert framework-specific trace formats into agentic-eval's
Trace/Span model so you can evaluate agents built with any framework.

    from agentic_eval.adapters import from_gemini, from_openai, from_langchain
    from agentic_eval.adapters import from_langfuse, from_mlflow

    trace = from_gemini(contents, response=gemini_response)
    result = run_evaluation(trace, skill="./SKILL.md")
"""

from .gemini_adapter import from_gemini
from .langchain_adapter import from_langchain
from .langgraph_adapter import from_langgraph
from .langfuse_adapter import from_langfuse
from .mlflow_adapter import from_mlflow
from .openai_adapter import from_openai
from .otel_adapter import from_otel

__all__ = [
    "from_gemini",
    "from_langchain",
    "from_langgraph",
    "from_langfuse",
    "from_mlflow",
    "from_openai",
    "from_otel",
]
