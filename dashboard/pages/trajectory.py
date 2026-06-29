"""Trajectory viewer dashboard page -- step-by-step trace inspection."""

from __future__ import annotations

import json
from pathlib import Path


def render(db_path: str) -> None:
    import streamlit as st
    import pandas as pd

    from skora.store import ResultStore

    st.header("Trajectory Viewer")

    if not Path(db_path).exists():
        st.warning("No results database found.")
        return

    store = ResultStore(db_path)

    try:
        results = store.query(limit=100)
        if not results:
            st.info("No evaluation results to display.")
            return

        options = [
            f"{r.get('id', '')[:8]} | {r.get('skill_name', 'unknown')} | "
            f"{r.get('verdict', '').upper()} ({r.get('overall_score', 0):.3f})"
            for r in results
        ]

        selected_idx = st.selectbox(
            "Select an evaluation run",
            range(len(options)),
            format_func=lambda i: options[i],
        )

        if selected_idx is not None:
            result = results[selected_idx]
            _display_eval_detail(result)

    finally:
        store.close()


def _display_eval_detail(result: dict) -> None:
    import streamlit as st
    import pandas as pd

    verdict_colors = {"pass": "green", "fail": "red", "partial": "orange"}
    verdict = result.get("verdict", "unknown")
    color = verdict_colors.get(verdict, "gray")

    st.markdown(
        f"### Evaluation: `{result.get('id', '')[:8]}`  "
        f":{color}[**{verdict.upper()}**]"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Overall Score", f"{result.get('overall_score', 0):.3f}")
    with col2:
        st.metric("Skill", result.get("skill_name", "unknown"))
    with col3:
        st.metric("Version", result.get("skill_version_hash", "")[:8] or "N/A")

    st.subheader("Per-Metric Breakdown")
    metric_results = result.get("metric_results", [])
    if metric_results:
        metric_data = []
        for mr in metric_results:
            metric_data.append({
                "Metric": mr.get("metric_name", ""),
                "Score": mr.get("score", 0),
                "Passed": "Yes" if mr.get("passed", False) else "No",
                "Reason": mr.get("reason", "")[:100],
            })

        df = pd.DataFrame(metric_data)
        st.dataframe(df, use_container_width=True)

        scores = {m["Metric"]: m["Score"] for m in metric_data}
        chart_df = pd.DataFrame({"Metric": list(scores.keys()), "Score": list(scores.values())})
        st.bar_chart(chart_df.set_index("Metric"))

    st.subheader("Trace Summary")
    trace_summary = result.get("trace_summary")
    if trace_summary:
        if isinstance(trace_summary, str):
            trace_summary = json.loads(trace_summary)

        col1, col2 = st.columns(2)
        with col1:
            st.write("**Input:**")
            st.code(str(trace_summary.get("input", "N/A"))[:500])
        with col2:
            st.write("**Output:**")
            st.code(str(trace_summary.get("output", "N/A"))[:500])

        tool_calls = trace_summary.get("tool_calls", [])
        if tool_calls:
            st.write("**Tool Calls:**")
            for i, tc in enumerate(tool_calls, 1):
                st.markdown(f"  {i}. `{tc}`")

        st.write(
            f"**Spans:** {trace_summary.get('span_count', 'N/A')} | "
            f"**Duration:** {trace_summary.get('duration_ms', 'N/A')}ms"
        )

    st.subheader("Metric Details")
    for mr in metric_results:
        details = mr.get("details", {})
        if details:
            with st.expander(f"{mr.get('metric_name', '')} -- Details"):
                st.json(details)

    st.subheader("Raw Metadata")
    metadata = result.get("metadata", {})
    if metadata:
        st.json(metadata)
