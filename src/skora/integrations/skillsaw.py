"""Integration with the skillsaw CLI for quality checks (Pillar 4)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from ..models import QualityReport, QualityViolation, Severity

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {
    "error": Severity.CRITICAL,
    "warning": Severity.WARNING,
    "info": Severity.INFO,
}


class ToolNotInstalledError(Exception):
    """Raised when a required external tool is not installed."""


def _ensure_skillsaw() -> str:
    """Return the path to the skillsaw binary, or raise."""
    path = shutil.which("skillsaw")
    if path is None:
        raise ToolNotInstalledError(
            "skillsaw is not installed. "
            "Install it with: pip install 'skillsaw>=0.14'"
        )
    return path


def run_quality_check(path: str | Path, fix: bool = False) -> QualityReport:
    """Run skillsaw lint on a skill directory or file.

    Args:
        path: Path to a SKILL.md file or directory containing one.
        fix: If True, pass --fix to auto-fix violations.

    Returns:
        QualityReport with grade, violations, and counts.

    Raises:
        ToolNotInstalledError: If skillsaw is not on PATH.
    """
    skillsaw_bin = _ensure_skillsaw()
    skill_path = Path(path).resolve()

    cmd = [skillsaw_bin, "lint", "--format", "json"]
    if fix:
        cmd.append("--fix")
    cmd.append(str(skill_path))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        logger.error("skillsaw timed out after 60s on %s", skill_path)
        return QualityReport(
            skill_path=str(skill_path),
            skill_name=skill_path.stem,
            grade="U",
        )

    raw = proc.stdout.strip()
    if not raw:
        logger.warning("skillsaw produced no output for %s (exit %d)", skill_path, proc.returncode)
        return QualityReport(
            skill_path=str(skill_path),
            skill_name=skill_path.stem,
            grade="U",
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse skillsaw JSON output: %s", exc)
        return QualityReport(
            skill_path=str(skill_path),
            skill_name=skill_path.stem,
            grade="U",
        )

    return _parse_skillsaw_output(data, str(skill_path))


def _parse_skillsaw_output(data: dict, skill_path: str) -> QualityReport:
    """Convert raw skillsaw JSON into a QualityReport."""
    violations: list[QualityViolation] = []
    error_count = 0
    warning_count = 0
    info_count = 0

    for item in data.get("violations", data.get("results", [])):
        raw_sev = item.get("severity", "info").lower()
        severity = _SEVERITY_MAP.get(raw_sev, Severity.INFO)

        violation = QualityViolation(
            rule_id=item.get("rule", item.get("rule_id", "unknown")),
            severity=severity,
            message=item.get("message", ""),
            file_path=item.get("file", item.get("file_path")),
            line_number=item.get("line", item.get("line_number")),
            fixable=item.get("fixable", False),
        )
        violations.append(violation)

        if severity == Severity.CRITICAL:
            error_count += 1
        elif severity == Severity.WARNING:
            warning_count += 1
        else:
            info_count += 1

    skill_name = data.get("skill_name", Path(skill_path).stem)
    grade = data.get("grade", "U")
    spec_compliant = data.get("spec_compliant", data.get("compliant", False))

    return QualityReport(
        skill_path=skill_path,
        skill_name=skill_name,
        grade=grade,
        violations=violations,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        spec_compliant=spec_compliant,
    )
