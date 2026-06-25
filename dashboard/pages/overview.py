"""Overview dashboard page -- aggregate scores, pass/fail rates, trends."""

from __future__ import annotations

from pathlib import Path


def render(db_path: str) -> None:
    import streamlit as st
    import pandas as pd

    from agentic_eval.store import ResultStore

    st.header("Evaluation Overview")

    if not Path(db_path).exists():
        st.warning("No results database found. Run some evaluations first.")
        st.code("pip install agentic-eval\n\n# Then in your code:\nfrom agentic_eval import evaluate\n\n@evaluate(skill='./SKILL.md')\ndef my_agent(query):\n    ...", language="python")
        return

    store = ResultStore(db_path)

    try:
        stats = store.get_stats()

        if not stats or stats.get("total_evals", 0) == 0:
            st.info("No evaluation results yet. Run your first evaluation!")
            return

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Evaluations", stats.get("total_evals", 0))
        with col2:
            avg_score = stats.get("avg_score", 0) or 0
            st.metric("Average Score", f"{avg_score:.1%}")
        with col3:
            passed = stats.get("passed", 0) or 0
            total = stats.get("total_evals", 1) or 1
            st.metric("Pass Rate", f"{passed / total:.1%}")
        with col4:
            st.metric("Unique Skills", stats.get("unique_skills", 0))

        st.divider()

        results = store.query(limit=200)
        if results:
            st.subheader("Score Distribution")

            scores = [r.get("overall_score", 0) for r in results]
            df_scores = pd.DataFrame({"Score": scores})
            st.bar_chart(df_scores["Score"].value_counts(bins=10).sort_index())

            st.subheader("Verdict Breakdown")
            verdicts = [r.get("verdict", "unknown") for r in results]
            df_verdicts = pd.DataFrame({"Verdict": verdicts})
            verdict_counts = df_verdicts["Verdict"].value_counts()
            st.bar_chart(verdict_counts)

            st.subheader("Score Trend Over Time")
            trend_data = []
            for r in results:
                trend_data.append({
                    "Timestamp": r.get("timestamp", "")[:10],
                    "Score": r.get("overall_score", 0),
                })
            if trend_data:
                df_trend = pd.DataFrame(trend_data)
                df_trend = df_trend.groupby("Timestamp")["Score"].mean().reset_index()
                st.line_chart(df_trend.set_index("Timestamp"))

            st.subheader("Per-Skill Performance")
            skill_data: dict[str, list[float]] = {}
            for r in results:
                name = r.get("skill_name", "unknown")
                skill_data.setdefault(name, []).append(r.get("overall_score", 0))

            skill_summary = []
            for name, scores_list in skill_data.items():
                skill_summary.append({
                    "Skill": name,
                    "Avg Score": f"{sum(scores_list) / len(scores_list):.3f}",
                    "Evals": len(scores_list),
                    "Best": f"{max(scores_list):.3f}",
                    "Worst": f"{min(scores_list):.3f}",
                })

            st.dataframe(pd.DataFrame(skill_summary), use_container_width=True)

            st.subheader("Recent Evaluations")
            recent = results[:20]
            table_data = []
            for r in recent:
                table_data.append({
                    "ID": r.get("id", "")[:8],
                    "Skill": r.get("skill_name", ""),
                    "Verdict": r.get("verdict", "").upper(),
                    "Score": f"{r.get('overall_score', 0):.3f}",
                    "Timestamp": r.get("timestamp", "")[:19],
                })
            st.dataframe(pd.DataFrame(table_data), use_container_width=True)

    finally:
        store.close()
