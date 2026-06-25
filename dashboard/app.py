"""Streamlit dashboard entry point for agentic-eval."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import streamlit as st

    st.set_page_config(
        page_title="agentic-eval Dashboard",
        page_icon="chart_with_upwards_trend",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    db_path = _get_db_path()

    st.sidebar.title("agentic-eval")
    st.sidebar.caption("Skill Evaluation Dashboard")

    page = st.sidebar.radio(
        "Navigate",
        ["Overview", "Trajectory Viewer", "Skill Comparison", "Security Scans"],
    )

    if page == "Overview":
        from dashboard.pages.overview import render
        render(db_path)
    elif page == "Trajectory Viewer":
        from dashboard.pages.trajectory import render
        render(db_path)
    elif page == "Skill Comparison":
        from dashboard.pages.comparison import render
        render(db_path)
    elif page == "Security Scans":
        from dashboard.pages.security import render
        render(db_path)


def _get_db_path() -> str:
    for i, arg in enumerate(sys.argv):
        if arg == "--db" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return "./agentic_eval_results.db"


if __name__ == "__main__":
    main()
