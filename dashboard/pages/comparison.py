"""Skill comparison dashboard page -- side-by-side version comparison."""

from __future__ import annotations

from pathlib import Path


def render(db_path: str) -> None:
    import streamlit as st
    import pandas as pd

    from agentic_eval.store import ResultStore

    st.header("Skill Version Comparison")

    if not Path(db_path).exists():
        st.warning("No results database found.")
        return

    store = ResultStore(db_path)

    try:
        comparisons = store.get_comparisons()

        if not comparisons:
            st.info(
                "No comparison results yet. Compare skills using:\n\n"
                "```python\n"
                "from agentic_eval import compare_skills\n"
                "result = compare_skills(skill_a, skill_b, traces_a=..., traces_b=...)\n"
                "```"
            )

            _render_adhoc_comparison(store)
            return

        for comp in comparisons:
            _display_comparison(comp)

    finally:
        store.close()


def _display_comparison(comp: dict) -> None:
    import streamlit as st
    import pandas as pd

    verdict = comp.get("verdict", "no_difference")
    verdict_display = {
        "a_better": "Skill A is Better",
        "b_better": "Skill B is Better",
        "no_difference": "No Significant Difference",
    }

    verdict_colors = {
        "a_better": "blue",
        "b_better": "green",
        "no_difference": "orange",
    }

    color = verdict_colors.get(verdict, "gray")

    st.markdown(f"### :{color}[{verdict_display.get(verdict, verdict)}]")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Skill A", Path(comp.get("skill_a_path", "")).name or "A")
    with col2:
        st.metric("Skill B", Path(comp.get("skill_b_path", "")).name or "B")
    with col3:
        lift = comp.get("lift", 0)
        st.metric("Lift", f"{lift:+.4f}", delta=f"{lift:+.4f}")

    per_metric = comp.get("per_metric", [])
    if per_metric:
        st.subheader("Per-Metric Comparison")

        metric_data = []
        for m in per_metric:
            metric_data.append({
                "Metric": m.get("metric_name", ""),
                "Score A": f"{m.get('score_a', 0):.4f}",
                "Score B": f"{m.get('score_b', 0):.4f}",
                "Delta": f"{m.get('delta', 0):+.4f}",
                "Winner": m.get("winner", "-").upper() or "-",
            })

        st.dataframe(pd.DataFrame(metric_data), use_container_width=True)

        chart_data = pd.DataFrame({
            "Metric": [m.get("metric_name", "") for m in per_metric],
            "Skill A": [m.get("score_a", 0) for m in per_metric],
            "Skill B": [m.get("score_b", 0) for m in per_metric],
        }).set_index("Metric")

        st.bar_chart(chart_data)

    st.caption(
        f"Trials: {comp.get('trials', 'N/A')} | "
        f"Timestamp: {comp.get('timestamp', '')[:19]}"
    )
    st.divider()


def _render_adhoc_comparison(store) -> None:
    import streamlit as st
    import pandas as pd

    st.subheader("Compare Existing Results")

    results = store.query(limit=500)
    if not results:
        return

    skills = list({r.get("skill_name", "") for r in results if r.get("skill_name")})
    if len(skills) < 2:
        st.info("Need at least 2 different skills to compare.")
        return

    col1, col2 = st.columns(2)
    with col1:
        skill_a = st.selectbox("Skill A", skills, key="comp_a")
    with col2:
        remaining = [s for s in skills if s != skill_a]
        skill_b = st.selectbox("Skill B", remaining, key="comp_b")

    if skill_a and skill_b:
        results_a = [r for r in results if r.get("skill_name") == skill_a]
        results_b = [r for r in results if r.get("skill_name") == skill_b]

        if results_a and results_b:
            avg_a = sum(r.get("overall_score", 0) for r in results_a) / len(results_a)
            avg_b = sum(r.get("overall_score", 0) for r in results_b) / len(results_b)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(skill_a, f"{avg_a:.3f}", f"{len(results_a)} evals")
            with col2:
                st.metric(skill_b, f"{avg_b:.3f}", f"{len(results_b)} evals")
            with col3:
                delta = avg_b - avg_a
                st.metric("Delta", f"{delta:+.3f}")
