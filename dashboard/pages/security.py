"""Security scan dashboard page -- vulnerability findings and trends."""

from __future__ import annotations

from pathlib import Path


def render(db_path: str) -> None:
    import streamlit as st
    import pandas as pd

    from scora.store import ResultStore

    st.header("Security Scan Results")

    if not Path(db_path).exists():
        st.warning("No results database found.")
        return

    store = ResultStore(db_path)

    try:
        reports = store.get_security_reports()

        if not reports:
            st.info(
                "No security scans yet. Scan a skill with:\n\n"
                "```bash\nscora security ./SKILL.md\n```\n\n"
                "Or in Python:\n"
                "```python\n"
                "from scora import scan_security\n"
                "report = scan_security('./SKILL.md')\n"
                "```"
            )
            return

        _render_summary(reports)
        st.divider()

        for report in reports:
            _render_report(report)

    finally:
        store.close()


def _render_summary(reports: list[dict]) -> None:
    import streamlit as st

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Scans", len(reports))
    with col2:
        grades = [r.get("grade", "?") for r in reports]
        a_count = grades.count("A")
        st.metric("Grade A Skills", f"{a_count}/{len(reports)}")
    with col3:
        all_findings = []
        for r in reports:
            all_findings.extend(r.get("findings", []))
        critical = sum(1 for f in all_findings if f.get("severity") == "critical")
        st.metric("Critical Findings", critical)
    with col4:
        avg_score = sum(r.get("score", 0) for r in reports) / len(reports) if reports else 0
        st.metric("Average Score", f"{avg_score:.2f}")


def _render_report(report: dict) -> None:
    import streamlit as st
    import pandas as pd

    grade = report.get("grade", "?")
    grade_colors = {"A": "green", "B": "blue", "C": "orange", "D": "red", "F": "red"}
    color = grade_colors.get(grade, "gray")

    skill_name = report.get("skill_name", "Unknown")
    score = report.get("score", 0)

    with st.expander(
        f":{color}[**Grade {grade}**] | {skill_name} | Score: {score:.2f}",
        expanded=False,
    ):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Score", f"{score:.2f}")
        with col2:
            st.metric("Grade", grade)
        with col3:
            st.metric("Findings", len(report.get("findings", [])))

        findings = report.get("findings", [])
        if findings:
            st.subheader("Findings")

            severity_order = {"critical": 0, "warning": 1, "info": 2}
            findings_sorted = sorted(
                findings, key=lambda f: severity_order.get(f.get("severity", "info"), 3)
            )

            finding_data = []
            for f in findings_sorted:
                finding_data.append({
                    "Severity": f.get("severity", "").upper(),
                    "Category": f.get("category", ""),
                    "Description": f.get("description", ""),
                    "Line": f.get("line_number", "-"),
                    "Recommendation": f.get("recommendation", ""),
                })

            st.dataframe(pd.DataFrame(finding_data), use_container_width=True)

            st.subheader("Findings by Category")
            categories: dict[str, int] = {}
            for f in findings:
                cat = f.get("category", "unknown")
                categories[cat] = categories.get(cat, 0) + 1

            chart_df = pd.DataFrame({
                "Category": list(categories.keys()),
                "Count": list(categories.values()),
            }).set_index("Category")
            st.bar_chart(chart_df)

        else:
            st.success("No security findings detected!")

        st.caption(
            f"Skill path: {report.get('skill_path', 'N/A')} | "
            f"Scanned: {report.get('scanned_at', '')[:19]}"
        )
