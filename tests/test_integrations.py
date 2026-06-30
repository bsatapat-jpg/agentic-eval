"""Tests for external tool integrations (skillsaw, skillspector) and related API/models."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skora.integrations.skillsaw import (
    ToolNotInstalledError,
    run_quality_check,
)
from skora.integrations.skillspector import (
    is_skillspector_available,
    run_skillspector,
)
from skora.models import (
    ComparisonResult,
    EvalResult,
    FullEvalReport,
    QualityReport,
    QualityViolation,
    SecurityFinding,
    SecurityReport,
    Severity,
    Verdict,
)


# ---------------------------------------------------------------------------
# Sample JSON payloads returned by the external CLIs
# ---------------------------------------------------------------------------

SKILLSAW_SAMPLE_OUTPUT = json.dumps({
    "skill_name": "my-skill",
    "grade": "B",
    "spec_compliant": True,
    "violations": [
        {
            "rule": "SK001",
            "severity": "error",
            "message": "Missing required section: constraints",
            "file": "SKILL.md",
            "line": 1,
            "fixable": True,
        },
        {
            "rule": "SK012",
            "severity": "warning",
            "message": "Step description too vague",
            "file": "SKILL.md",
            "line": 15,
            "fixable": False,
        },
        {
            "rule": "SK030",
            "severity": "info",
            "message": "Consider adding examples section",
            "file": "SKILL.md",
            "line": 20,
            "fixable": False,
        },
    ],
})

SKILLSPECTOR_SAMPLE_OUTPUT = json.dumps({
    "skill_name": "my-skill",
    "risk_score": 25,
    "grade": "B",
    "findings": [
        {
            "severity": "high",
            "category": "prompt_injection",
            "message": "Potential instruction override",
            "file": "SKILL.md",
            "line": 10,
            "recommendation": "Rephrase to avoid injection surface",
        },
        {
            "severity": "low",
            "category": "missing_guardrails",
            "message": "No explicit constraints section",
            "file": "SKILL.md",
            "line": 1,
            "recommendation": "Add constraints",
        },
    ],
})


# ===================================================================
# 1. skillsaw wrapper tests
# ===================================================================


class TestSkillsawWrapper:
    """Tests for src/skora/integrations/skillsaw.py (mocked subprocess)."""

    @patch("skora.integrations.skillsaw.shutil.which", return_value="/usr/bin/skillsaw")
    @patch("skora.integrations.skillsaw.subprocess.run")
    def test_successful_lint_run(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SKILLSAW_SAMPLE_OUTPUT,
            returncode=0,
        )

        report = run_quality_check(tmp_path / "SKILL.md")

        assert isinstance(report, QualityReport)
        assert report.grade == "B"
        assert report.skill_name == "my-skill"
        assert report.spec_compliant is True
        assert report.error_count == 1
        assert report.warning_count == 1
        assert report.info_count == 1
        assert len(report.violations) == 3
        assert report.violations[0].rule_id == "SK001"
        assert report.violations[0].severity == Severity.CRITICAL
        assert report.violations[0].fixable is True
        assert report.violations[1].severity == Severity.WARNING
        assert report.violations[2].severity == Severity.INFO

    @patch("skora.integrations.skillsaw.shutil.which", return_value=None)
    def test_tool_not_installed_error(self, mock_which):
        with pytest.raises(ToolNotInstalledError, match="skillsaw is not installed"):
            run_quality_check("/some/SKILL.md")

    @patch("skora.integrations.skillsaw.shutil.which", return_value="/usr/bin/skillsaw")
    @patch("skora.integrations.skillsaw.subprocess.run")
    def test_non_zero_exit_with_empty_stdout(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            stdout="",
            returncode=1,
        )

        report = run_quality_check(tmp_path / "SKILL.md")

        assert isinstance(report, QualityReport)
        assert report.grade == "U"

    @patch("skora.integrations.skillsaw.shutil.which", return_value="/usr/bin/skillsaw")
    @patch("skora.integrations.skillsaw.subprocess.run")
    def test_non_zero_exit_with_valid_json(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SKILLSAW_SAMPLE_OUTPUT,
            returncode=1,
        )

        report = run_quality_check(tmp_path / "SKILL.md")

        assert isinstance(report, QualityReport)
        assert report.grade == "B"
        assert len(report.violations) == 3

    @patch("skora.integrations.skillsaw.shutil.which", return_value="/usr/bin/skillsaw")
    @patch("skora.integrations.skillsaw.subprocess.run")
    def test_fix_passthrough(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SKILLSAW_SAMPLE_OUTPUT,
            returncode=0,
        )

        run_quality_check(tmp_path / "SKILL.md", fix=True)

        cmd = mock_run.call_args[0][0]
        assert "--fix" in cmd
        assert cmd[1] == "lint"
        assert "--format" in cmd and "json" in cmd

    @patch("skora.integrations.skillsaw.shutil.which", return_value="/usr/bin/skillsaw")
    @patch("skora.integrations.skillsaw.subprocess.run")
    def test_fix_not_passed_by_default(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SKILLSAW_SAMPLE_OUTPUT,
            returncode=0,
        )

        run_quality_check(tmp_path / "SKILL.md", fix=False)

        cmd = mock_run.call_args[0][0]
        assert "--fix" not in cmd

    @patch("skora.integrations.skillsaw.shutil.which", return_value="/usr/bin/skillsaw")
    @patch("skora.integrations.skillsaw.subprocess.run")
    def test_timeout_returns_grade_u(self, mock_run, mock_which, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="skillsaw", timeout=60)

        report = run_quality_check(tmp_path / "SKILL.md")

        assert report.grade == "U"
        assert len(report.violations) == 0


# ===================================================================
# 2. skillspector wrapper tests
# ===================================================================


class TestSkillspectorWrapper:
    """Tests for src/skora/integrations/skillspector.py (mocked subprocess)."""

    @patch("skora.integrations.skillspector.shutil.which", return_value="/usr/bin/skillspector")
    @patch("skora.integrations.skillspector.subprocess.run")
    def test_successful_scan(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SKILLSPECTOR_SAMPLE_OUTPUT,
            returncode=0,
        )

        report = run_skillspector(tmp_path / "SKILL.md")

        assert isinstance(report, SecurityReport)
        assert report.skill_name == "my-skill"
        assert report.grade == "B"
        assert report.score == pytest.approx(0.75)
        assert len(report.findings) == 2
        assert report.findings[0].severity == Severity.CRITICAL
        assert report.findings[0].category == "prompt_injection"
        assert report.findings[1].severity == Severity.INFO

    @patch("skora.integrations.skillspector.shutil.which", return_value=None)
    def test_fallback_to_builtin_scanner(self, mock_which, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Safe Skill\n\nA safe skill.\n")

        report = run_skillspector(skill_file)

        assert isinstance(report, SecurityReport)
        assert report.score >= 0.0
        assert report.grade in ("A", "B", "C", "D", "F")

    @patch("skora.integrations.skillspector.shutil.which", return_value="/usr/bin/skillspector")
    @patch("skora.integrations.skillspector.subprocess.run")
    def test_use_llm_flag_true(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SKILLSPECTOR_SAMPLE_OUTPUT,
            returncode=0,
        )

        run_skillspector(tmp_path / "SKILL.md", use_llm=True)

        cmd = mock_run.call_args[0][0]
        assert "--no-llm" not in cmd

    @patch("skora.integrations.skillspector.shutil.which", return_value="/usr/bin/skillspector")
    @patch("skora.integrations.skillspector.subprocess.run")
    def test_use_llm_flag_false(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=SKILLSPECTOR_SAMPLE_OUTPUT,
            returncode=0,
        )

        run_skillspector(tmp_path / "SKILL.md", use_llm=False)

        cmd = mock_run.call_args[0][0]
        assert "--no-llm" in cmd

    @patch("skora.integrations.skillspector.shutil.which", return_value="/usr/bin/skillspector")
    @patch("skora.integrations.skillspector.subprocess.run")
    def test_empty_output_returns_default(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            stdout="",
            returncode=1,
        )

        report = run_skillspector(tmp_path / "SKILL.md")

        assert isinstance(report, SecurityReport)
        assert len(report.findings) == 0

    @patch("skora.integrations.skillspector.shutil.which")
    def test_is_skillspector_available(self, mock_which):
        mock_which.return_value = "/usr/bin/skillspector"
        assert is_skillspector_available() is True

        mock_which.return_value = None
        assert is_skillspector_available() is False

    @patch("skora.integrations.skillspector.shutil.which", return_value="/usr/bin/skillspector")
    @patch("skora.integrations.skillspector.subprocess.run")
    def test_timeout_returns_default(self, mock_run, mock_which, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="skillspector", timeout=120)

        report = run_skillspector(tmp_path / "SKILL.md")

        assert isinstance(report, SecurityReport)
        assert len(report.findings) == 0


# ===================================================================
# 3. Model construction tests
# ===================================================================


class TestQualityModels:
    """Tests for QualityViolation and QualityReport Pydantic models."""

    def test_quality_violation_construction(self):
        v = QualityViolation(
            rule_id="SK001",
            severity=Severity.CRITICAL,
            message="Missing constraints",
            file_path="SKILL.md",
            line_number=5,
            fixable=True,
        )
        assert v.rule_id == "SK001"
        assert v.severity == Severity.CRITICAL
        assert v.fixable is True

    def test_quality_violation_defaults(self):
        v = QualityViolation(
            rule_id="SK002",
            severity=Severity.INFO,
            message="Consider adding examples",
        )
        assert v.file_path is None
        assert v.line_number is None
        assert v.fixable is False

    def test_quality_report_construction(self):
        violations = [
            QualityViolation(rule_id="SK001", severity=Severity.CRITICAL, message="err"),
            QualityViolation(rule_id="SK002", severity=Severity.WARNING, message="warn"),
        ]
        report = QualityReport(
            skill_path="/path/SKILL.md",
            skill_name="test-skill",
            grade="B",
            violations=violations,
            error_count=1,
            warning_count=1,
            info_count=0,
            spec_compliant=True,
        )
        assert report.grade == "B"
        assert report.total_violations == 2
        assert report.tool_used == "skillsaw"
        assert report.spec_compliant is True

    def test_quality_report_defaults(self):
        report = QualityReport(
            skill_path="/path/SKILL.md",
            skill_name="test-skill",
        )
        assert report.grade == "U"
        assert report.violations == []
        assert report.error_count == 0
        assert report.total_violations == 0
        assert report.spec_compliant is False


class TestFullEvalReport:
    """Tests for FullEvalReport model with mixed pillar results."""

    def test_construction_with_all_pillars(self):
        adherence = EvalResult(
            skill_name="test",
            verdict=Verdict.PASS,
            overall_score=0.92,
        )
        security = SecurityReport(
            skill_path="/path/SKILL.md",
            skill_name="test",
            grade="A",
            score=0.95,
        )
        quality = QualityReport(
            skill_path="/path/SKILL.md",
            skill_name="test",
            grade="B",
        )
        comparison = ComparisonResult(
            skill_a_path="/a",
            skill_b_path="/b",
        )

        report = FullEvalReport(
            skill_name="test",
            skill_path="/path/SKILL.md",
            adherence=adherence,
            security=security,
            quality=quality,
            comparison=comparison,
            overall_grade="A",
        )

        assert report.adherence is not None
        assert report.security is not None
        assert report.quality is not None
        assert report.comparison is not None
        assert report.overall_grade == "A"

    def test_construction_partial_pillars(self):
        report = FullEvalReport(
            skill_name="test",
            skill_path="/path/SKILL.md",
            security=SecurityReport(
                skill_path="/path/SKILL.md",
                skill_name="test",
                grade="A",
            ),
            overall_grade="A",
        )

        assert report.adherence is None
        assert report.security is not None
        assert report.quality is None
        assert report.comparison is None

    def test_default_grade_is_u(self):
        report = FullEvalReport(
            skill_name="test",
            skill_path="/path/SKILL.md",
        )
        assert report.overall_grade == "U"


# ===================================================================
# 4. API function delegation tests
# ===================================================================


class TestAPIFunctions:
    """Tests for check_quality(), scan_security_deep(), evaluate_skill_full()."""

    @patch("skora.integrations.skillsaw.run_quality_check")
    def test_check_quality_delegates(self, mock_rqc):
        expected = QualityReport(
            skill_path="/s/SKILL.md",
            skill_name="s",
            grade="A",
        )
        mock_rqc.return_value = expected

        from skora.api import check_quality

        result = check_quality("/s/SKILL.md", fix=True)

        mock_rqc.assert_called_once_with("/s/SKILL.md", fix=True)
        assert result is expected

    @patch("skora.integrations.skillspector.run_skillspector")
    def test_scan_security_deep_delegates(self, mock_rss):
        expected = SecurityReport(
            skill_path="/s/SKILL.md",
            skill_name="s",
            grade="A",
        )
        mock_rss.return_value = expected

        from skora.api import scan_security_deep

        result = scan_security_deep("/s/SKILL.md", use_llm=True)

        mock_rss.assert_called_once_with("/s/SKILL.md", use_llm=True)
        assert result is expected

    @patch("skora.api.check_quality")
    @patch("skora.api.scan_security_deep")
    def test_evaluate_skill_full_orchestrates(self, mock_sec, mock_qual, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Test Skill\n\nDo things.\n")

        mock_sec.return_value = SecurityReport(
            skill_path=str(skill_file),
            skill_name="SKILL",
            grade="A",
            score=0.95,
        )
        mock_qual.return_value = QualityReport(
            skill_path=str(skill_file),
            skill_name="SKILL",
            grade="B",
        )

        from skora.api import evaluate_skill_full

        report = evaluate_skill_full(skill_file)

        assert isinstance(report, FullEvalReport)
        assert report.security is not None
        assert report.quality is not None
        assert report.adherence is None
        mock_sec.assert_called_once()
        mock_qual.assert_called_once()

    @patch("skora.api.check_quality")
    @patch("skora.api.scan_security_deep")
    def test_evaluate_skill_full_grade_computed(self, mock_sec, mock_qual, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Test Skill\n\nDo things.\n")

        mock_sec.return_value = SecurityReport(
            skill_path=str(skill_file),
            skill_name="SKILL",
            grade="A",
            score=0.95,
        )
        mock_qual.return_value = QualityReport(
            skill_path=str(skill_file),
            skill_name="SKILL",
            grade="A",
        )

        from skora.api import evaluate_skill_full

        report = evaluate_skill_full(skill_file)

        assert report.overall_grade in ("A+", "A", "B", "C", "D", "F", "U")

    @patch("skora.api.check_quality", side_effect=Exception("quality failed"))
    @patch("skora.api.scan_security_deep", side_effect=Exception("security failed"))
    def test_evaluate_skill_full_handles_failures(self, mock_sec, mock_qual, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Test Skill\n\nDo things.\n")

        from skora.api import evaluate_skill_full

        report = evaluate_skill_full(skill_file)

        assert isinstance(report, FullEvalReport)
        assert report.security is None
        assert report.quality is None
        assert report.overall_grade == "U"
