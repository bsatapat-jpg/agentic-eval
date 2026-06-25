"""Results persistence -- SQLite store with JSON export."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import EvalResult, MetricResult, SecurityReport, ComparisonResult


class ResultStore:
    """SQLite-backed store for evaluation results.

    Usage:
        store = ResultStore("./eval_results.db")
        store.save(eval_result)
        results = store.query(skill_name="my-skill")
        store.export_json("./results.json")
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS eval_results (
        id TEXT PRIMARY KEY,
        skill_name TEXT,
        skill_path TEXT,
        skill_version_hash TEXT,
        verdict TEXT,
        overall_score REAL,
        metric_results TEXT,
        trace_summary TEXT,
        metadata TEXT,
        timestamp TEXT
    );

    CREATE TABLE IF NOT EXISTS security_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_path TEXT,
        skill_name TEXT,
        score REAL,
        grade TEXT,
        findings TEXT,
        scanned_at TEXT
    );

    CREATE TABLE IF NOT EXISTS comparison_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_a_path TEXT,
        skill_b_path TEXT,
        skill_a_hash TEXT,
        skill_b_hash TEXT,
        verdict TEXT,
        lift REAL,
        per_metric TEXT,
        trials INTEGER,
        timestamp TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_skill_name ON eval_results(skill_name);
    CREATE INDEX IF NOT EXISTS idx_timestamp ON eval_results(timestamp);
    CREATE INDEX IF NOT EXISTS idx_verdict ON eval_results(verdict);
    """

    def __init__(self, db_path: str | Path = "./agentic_eval_results.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30.0,
        )
        try:
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._init_schema()
        except Exception:
            self._conn.close()
            raise

    def _init_schema(self) -> None:
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()

    def save(self, result: EvalResult) -> str:
        """Save an evaluation result. Returns the result ID."""
        trace_summary = None
        if result.trace:
            trace_summary = json.dumps({
                "input": str(result.trace.input)[:1000],
                "output": str(result.trace.output)[:1000],
                "span_count": len(result.trace.spans),
                "tool_calls": [tc.name for tc in result.trace.tool_calls],
                "duration_ms": result.trace.duration_ms,
            })

        self._conn.execute(
            """INSERT OR REPLACE INTO eval_results
               (id, skill_name, skill_path, skill_version_hash, verdict,
                overall_score, metric_results, trace_summary, metadata, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.id,
                result.skill_name,
                result.skill_path,
                result.skill_version_hash,
                result.verdict.value,
                result.overall_score,
                json.dumps([mr.model_dump() for mr in result.metric_results], default=str),
                trace_summary,
                json.dumps(result.metadata, default=str),
                result.timestamp.isoformat(),
            ),
        )
        self._conn.commit()
        return result.id

    def save_security_report(self, report: SecurityReport) -> None:
        """Save a security scan report."""
        self._conn.execute(
            """INSERT INTO security_reports
               (skill_path, skill_name, score, grade, findings, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                report.skill_path,
                report.skill_name,
                report.score,
                report.grade,
                json.dumps([f.model_dump() for f in report.findings], default=str),
                report.scanned_at.isoformat(),
            ),
        )
        self._conn.commit()

    def save_comparison(self, result: ComparisonResult) -> None:
        """Save a comparison result."""
        self._conn.execute(
            """INSERT INTO comparison_results
               (skill_a_path, skill_b_path, skill_a_hash, skill_b_hash,
                verdict, lift, per_metric, trials, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.skill_a_path,
                result.skill_b_path,
                result.skill_a_hash,
                result.skill_b_hash,
                result.verdict.value,
                result.lift,
                json.dumps([m.model_dump() for m in result.per_metric], default=str),
                result.trials,
                result.timestamp.isoformat(),
            ),
        )
        self._conn.commit()

    def query(
        self,
        skill_name: str | None = None,
        verdict: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query evaluation results with optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if skill_name:
            conditions.append("skill_name = ?")
            params.append(skill_name)
        if verdict:
            conditions.append("verdict = ?")
            params.append(verdict)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""SELECT * FROM eval_results {where}
                    ORDER BY timestamp DESC LIMIT ? OFFSET ?"""
        params.extend([limit, offset])

        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            d["metric_results"] = json.loads(d["metric_results"]) if d["metric_results"] else []
            d["trace_summary"] = json.loads(d["trace_summary"]) if d["trace_summary"] else None
            d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
            results.append(d)

        return results

    def get_security_reports(self, skill_path: str | None = None) -> list[dict[str, Any]]:
        """Get security scan reports."""
        if skill_path:
            cursor = self._conn.execute(
                "SELECT * FROM security_reports WHERE skill_path = ? ORDER BY scanned_at DESC",
                (skill_path,),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM security_reports ORDER BY scanned_at DESC"
            )

        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d["findings"] = json.loads(d["findings"]) if d["findings"] else []
            results.append(d)
        return results

    def get_comparisons(self) -> list[dict[str, Any]]:
        """Get all comparison results."""
        cursor = self._conn.execute(
            "SELECT * FROM comparison_results ORDER BY timestamp DESC"
        )
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d["per_metric"] = json.loads(d["per_metric"]) if d["per_metric"] else []
            results.append(d)
        return results

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics."""
        cursor = self._conn.execute(
            """SELECT
                COUNT(*) as total_evals,
                AVG(overall_score) as avg_score,
                SUM(CASE WHEN verdict = 'pass' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN verdict = 'fail' THEN 1 ELSE 0 END) as failed,
                COUNT(DISTINCT skill_name) as unique_skills
               FROM eval_results"""
        )
        row = cursor.fetchone()
        return dict(row) if row else {}

    def export_json(self, output_path: str | Path) -> None:
        """Export all results to a JSON file."""
        data = {
            "eval_results": self.query(limit=10000),
            "security_reports": self.get_security_reports(),
            "comparisons": self.get_comparisons(),
            "stats": self.get_stats(),
        }

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2, default=str))

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> ResultStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
