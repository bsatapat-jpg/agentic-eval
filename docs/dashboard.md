# Dashboard

agentic-eval includes a Streamlit-based dashboard for exploring evaluation results visually.

## Setup

```bash
pip install agentic-eval[dashboard]
```

## Launch

```bash
agentic-eval dashboard
agentic-eval dashboard --port 8502
agentic-eval dashboard --db ./custom_results.db
```

Or programmatically:

```python
import subprocess
subprocess.run(["agentic-eval", "dashboard", "--port", "8501"])
```

## Pages

### Overview

Aggregate view of all evaluations:
- Total evaluations, pass rate, average score
- Score trend over time
- Per-skill breakdown
- Verdict distribution (pass / fail / partial)

### Trajectory Viewer

Drill into individual traces:
- Tree visualization of spans (tool calls, LLM calls, errors)
- Per-metric score breakdown
- Timeline view with durations
- Input/output inspection

### Comparison

Side-by-side skill version analysis:
- Per-metric score comparison
- Lift calculation
- Verdict history

### Security

Security scan results:
- Grade and score trends
- Finding breakdown by severity
- Per-skill security comparison
