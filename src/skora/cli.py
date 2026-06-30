"""CLI entry point for skora."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .evaluators.security import SecurityEvaluator
from .store import ResultStore

console = Console()


@click.group()
@click.version_option(package_name="skora")
def main() -> None:
    """skora: Trajectory-based evaluation for AI agent skills."""
    pass


@main.command()
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output JSON file path")
@click.option("--db", type=click.Path(), default="./skora_results.db", help="Database path")
@click.option("--fail-on", type=click.Choice(["critical", "warning", "any"]),
              default=None, help="Exit non-zero if findings at this severity or above")
def security(skill_path: str, output: str | None, db: str, fail_on: str | None) -> None:
    """Scan a SKILL.md for security vulnerabilities."""
    console.print(f"\n[bold]Scanning:[/bold] {skill_path}\n")

    evaluator = SecurityEvaluator()
    report = evaluator.scan_skill(skill_path)

    _display_security_report(report)

    with ResultStore(db) as store:
        store.save_security_report(report)
        console.print(f"\n[dim]Results saved to {db}[/dim]")

    if output:
        Path(output).write_text(
            json.dumps(report.model_dump(), indent=2, default=str)
        )
        console.print(f"[dim]Report exported to {output}[/dim]")

    if fail_on:
        if fail_on == "critical" and report.critical_count > 0:
            sys.exit(1)
        elif fail_on == "warning" and (report.critical_count + report.warning_count) > 0:
            sys.exit(1)
        elif fail_on == "any" and len(report.findings) > 0:
            sys.exit(1)


@main.command()
@click.option("--skill", "-s", type=str, help="Filter by skill name")
@click.option("--verdict", "-v", type=click.Choice(["pass", "fail", "partial"]))
@click.option("--limit", "-l", type=int, default=20)
@click.option("--db", type=click.Path(), default="./skora_results.db")
@click.option("--export", "-e", type=click.Path(), help="Export to JSON file")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]),
              default="table", help="Output format")
def results(
    skill: str | None,
    verdict: str | None,
    limit: int,
    db: str,
    export: str | None,
    output_format: str,
) -> None:
    """View evaluation results."""
    db_path = Path(db)
    if not db_path.exists():
        console.print("[yellow]No results database found. Run some evaluations first.[/yellow]")
        return

    with ResultStore(db) as store:
        stats = store.get_stats()
        rows = store.query(skill_name=skill, verdict=verdict, limit=limit)

        if output_format == "json":
            click.echo(json.dumps({"stats": stats, "results": rows}, indent=2, default=str))
        else:
            _display_stats(stats)
            if rows:
                _display_results_table(rows)
            else:
                console.print("[dim]No results found matching filters.[/dim]")

        if export:
            store.export_json(export)
            console.print(f"\n[dim]Results exported to {export}[/dim]")


@main.command()
@click.option("--db", type=click.Path(), default="./skora_results.db")
@click.option("--port", "-p", type=int, default=8501)
def dashboard(db: str, port: int) -> None:
    """Launch the Streamlit evaluation dashboard."""
    try:
        import streamlit
    except ImportError:
        console.print(
            "[red]Streamlit not installed.[/red] Install with: "
            "[bold]pip install skora\\[dashboard][/bold]"
        )
        sys.exit(1)

    import subprocess

    try:
        import dashboard
        dashboard_app = Path(dashboard.__file__).parent / "app.py"
    except ImportError:
        console.print(
            "[red]Dashboard package not found.[/red] "
            "Ensure the dashboard/ folder is present at the project root "
            "and the package is installed: [bold]pip install -e .[/bold]"
        )
        sys.exit(1)

    if not dashboard_app.exists():
        console.print("[red]Dashboard app.py not found.[/red]")
        sys.exit(1)

    console.print(f"\n[bold green]Launching dashboard[/bold green] on port {port}...")
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run",
            str(dashboard_app),
            "--server.port", str(port),
            "--",
            "--db", db,
        ],
        check=True,
    )


@main.command()
@click.argument("skill_a", type=click.Path(exists=True))
@click.argument("skill_b", type=click.Path(exists=True))
@click.option("--db", type=click.Path(), default="./skora_results.db", help="Database path")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]),
              default="table", help="Output format")
def compare(skill_a: str, skill_b: str, db: str, output_format: str) -> None:
    """Compare two SKILL.md files (security + metrics from stored evaluations)."""
    console.print(f"\n[bold]Comparing:[/bold] {skill_a} vs {skill_b}\n")

    evaluator = SecurityEvaluator()
    report_a = evaluator.scan_skill(skill_a)
    report_b = evaluator.scan_skill(skill_b)

    if output_format == "json":
        click.echo(json.dumps({
            "skill_a": {"name": report_a.skill_name, "grade": report_a.grade,
                        "score": report_a.score, "critical": report_a.critical_count,
                        "warnings": report_a.warning_count, "findings": len(report_a.findings)},
            "skill_b": {"name": report_b.skill_name, "grade": report_b.grade,
                        "score": report_b.score, "critical": report_b.critical_count,
                        "warnings": report_b.warning_count, "findings": len(report_b.findings)},
            "delta": report_b.score - report_a.score,
        }, indent=2))
        return

    sec_table = Table(title="Security Comparison")
    sec_table.add_column("Attribute", style="cyan")
    sec_table.add_column("Skill A", style="yellow")
    sec_table.add_column("Skill B", style="green")

    sec_table.add_row("Name", report_a.skill_name, report_b.skill_name)
    sec_table.add_row("Grade", report_a.grade, report_b.grade)
    sec_table.add_row("Score", f"{report_a.score:.2f}", f"{report_b.score:.2f}")
    sec_table.add_row("Critical", str(report_a.critical_count), str(report_b.critical_count))
    sec_table.add_row("Warnings", str(report_a.warning_count), str(report_b.warning_count))
    sec_table.add_row("Total Findings", str(len(report_a.findings)), str(len(report_b.findings)))

    console.print(sec_table)

    db_path = Path(db)
    if db_path.exists():
        with ResultStore(db) as store:
            from .skill_parser import parse_skill
            spec_a = parse_skill(skill_a)
            spec_b = parse_skill(skill_b)
            results_a = store.query(skill_name=spec_a.name, limit=100)
            results_b = store.query(skill_name=spec_b.name, limit=100)

            if results_a and results_b:
                avg_a = sum(r["overall_score"] for r in results_a) / len(results_a)
                avg_b = sum(r["overall_score"] for r in results_b) / len(results_b)

                eval_table = Table(title="Evaluation Comparison (from stored results)")
                eval_table.add_column("Attribute", style="cyan")
                eval_table.add_column("Skill A", style="yellow")
                eval_table.add_column("Skill B", style="green")
                eval_table.add_row("Evaluations", str(len(results_a)), str(len(results_b)))
                eval_table.add_row("Avg Score", f"{avg_a:.3f}", f"{avg_b:.3f}")
                eval_table.add_row("Delta", "", f"{avg_b - avg_a:+.3f}")
                console.print(eval_table)

    delta = report_b.score - report_a.score
    if delta > 0.05:
        console.print("\n[green bold]Verdict: Skill B is more secure[/green bold]")
    elif delta < -0.05:
        console.print("\n[red bold]Verdict: Skill A is more secure[/red bold]")
    else:
        console.print("\n[yellow bold]Verdict: Similar security profiles[/yellow bold]")


@main.command()
@click.option("--config", "-c", "config_path", type=click.Path(), default=None,
              help="Path to skora.yaml config file")
@click.option("--fail-below", type=float, default=None,
              help="Override: fail if overall score is below this threshold")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]),
              default=None, help="Override output format")
def ci(config_path: str | None, fail_below: float | None, output_format: str | None) -> None:
    """Run evaluation from a YAML config file (CI/CD mode).

    Reads skora.yaml, runs test cases against the configured agent,
    evaluates results, and exits non-zero if thresholds are not met.
    """
    from .config import load_config

    try:
        cfg = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    fmt = output_format or cfg.ci.output_format or "table"
    threshold = fail_below if fail_below is not None else cfg.ci.fail_below

    console.print(f"\n[bold]Project:[/bold] {cfg.project or 'unnamed'}")
    console.print(f"[bold]Skills:[/bold]  {len(cfg.skills)}")
    console.print(f"[bold]Tests:[/bold]   {len(cfg.test_cases)}\n")

    if not cfg.has_test_cases and not cfg.skills:
        console.print("[yellow]No test cases or skills configured. Nothing to evaluate.[/yellow]")
        sys.exit(0)

    all_results: list[dict] = []
    exit_code = 0

    if cfg.skills and not cfg.has_test_cases:
        from .evaluators.security import SecurityEvaluator
        evaluator = SecurityEvaluator()
        for skill_cfg in cfg.skills:
            report = evaluator.scan_skill(skill_cfg.path)
            if fmt == "table":
                _display_security_report(report)
            else:
                click.echo(json.dumps(report.model_dump(), indent=2, default=str))

            for metric_name, min_score in skill_cfg.thresholds.items():
                if metric_name == "security" and report.score < min_score:
                    console.print(
                        f"[red]FAIL:[/red] {skill_cfg.path} security score "
                        f"{report.score:.2f} < {min_score}"
                    )
                    exit_code = 1

    if cfg.has_test_cases:
        from .api import run_evaluation as _run_eval
        from .models import Trace

        if cfg.has_agent:
            from .agent_evaluator import AgentEvaluator

            agent_eval = AgentEvaluator(config=cfg.agent)

            for i, tc in enumerate(cfg.test_cases):
                skill_path = tc.skill or (cfg.skills[0].path if cfg.skills else None)
                skill_thresholds = {}
                skill_weights = {}
                if cfg.skills:
                    matching = [s for s in cfg.skills if s.path == skill_path]
                    if matching:
                        skill_thresholds = matching[0].thresholds
                        skill_weights = matching[0].weights

                merged_thresholds = {**skill_thresholds}
                merged_weights = {**cfg.metrics.weights, **skill_weights}

                try:
                    response = agent_eval.call_agent(tc.input)
                    trace = agent_eval.response_to_trace(tc.input, response)
                except Exception as e:
                    console.print(f"[red]Test {i+1} ERROR:[/red] {e}")
                    exit_code = 1
                    continue

                result = _run_eval(
                    trace=trace,
                    skill=skill_path,
                    metrics=cfg.metrics.enabled,
                    thresholds=merged_thresholds or None,
                    weights=merged_weights or None,
                    use_llm_judge=cfg.metrics.use_llm_judge,
                    save=cfg.ci.save,
                    db_path=cfg.ci.db_path,
                )

                entry = {
                    "test": i + 1,
                    "input": tc.input[:60],
                    "verdict": result.verdict.value,
                    "score": result.overall_score,
                    "metrics": {m.metric_name: m.score for m in result.metric_results},
                }
                all_results.append(entry)

                if threshold and result.overall_score < threshold:
                    exit_code = 1
                if cfg.ci.fail_on_any_metric_below:
                    for mr in result.metric_results:
                        if mr.score < cfg.ci.fail_on_any_metric_below:
                            exit_code = 1
        else:
            console.print("[yellow]Test cases defined but no agent URL configured.[/yellow]")
            console.print("[dim]Add an 'agent:' section to your config to run live evaluation.[/dim]\n")

    if all_results:
        if fmt == "json":
            output = {"project": cfg.project, "results": all_results}
            json_str = json.dumps(output, indent=2, default=str)
            click.echo(json_str)
            if cfg.ci.output_file:
                Path(cfg.ci.output_file).write_text(json_str)
        else:
            table = Table(title="Evaluation Results")
            table.add_column("#", justify="right", style="dim")
            table.add_column("Input", max_width=50)
            table.add_column("Verdict", style="bold")
            table.add_column("Score", justify="right")

            verdict_colors = {"pass": "green", "fail": "red", "partial": "yellow"}

            for r in all_results:
                v = r["verdict"]
                color = verdict_colors.get(v, "white")
                table.add_row(
                    str(r["test"]),
                    r["input"],
                    f"[{color}]{v.upper()}[/{color}]",
                    f"{r['score']:.3f}",
                )

            console.print(table)

            avg = sum(r["score"] for r in all_results) / len(all_results)
            passed = sum(1 for r in all_results if r["verdict"] == "pass")
            console.print(
                f"\n[bold]Pass rate:[/bold] {passed}/{len(all_results)}  "
                f"[bold]Avg score:[/bold] {avg:.3f}"
            )

            if cfg.ci.output_file:
                Path(cfg.ci.output_file).write_text(
                    json.dumps({"project": cfg.project, "results": all_results}, indent=2, default=str)
                )

    if exit_code:
        console.print("\n[red bold]CI CHECK FAILED[/red bold]")
    else:
        console.print("\n[green bold]CI CHECK PASSED[/green bold]")

    sys.exit(exit_code)


@main.command()
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--fix", is_flag=True, default=False, help="Auto-fix violations where possible")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]),
              default="table", help="Output format")
@click.option("--fail-on", type=click.Choice(["error", "warning", "any"]),
              default=None, help="Exit non-zero if violations at this severity or above")
def quality(skill_path: str, fix: bool, output_format: str, fail_on: str | None) -> None:
    """Run quality checks on a SKILL.md (Pillar 4 — requires skillsaw)."""
    from .integrations.skillsaw import run_quality_check

    console.print(f"\n[bold]Quality check:[/bold] {skill_path}\n")

    try:
        report = run_quality_check(skill_path, fix=fix)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        console.print("[dim]Install with: pip install 'skora[quality]'[/dim]")
        sys.exit(1)

    if output_format == "json":
        click.echo(json.dumps(report.model_dump(), indent=2, default=str))
    else:
        _display_quality_report(report)

    if fail_on:
        if fail_on == "error" and report.error_count > 0:
            sys.exit(1)
        elif fail_on == "warning" and (report.error_count + report.warning_count) > 0:
            sys.exit(1)
        elif fail_on == "any" and len(report.violations) > 0:
            sys.exit(1)


@main.command()
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--use-llm", is_flag=True, default=False,
              help="Enable LLM-assisted analysis (requires API key)")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "sarif"]),
              default="table", help="Output format")
@click.option("--fail-on", type=click.Choice(["critical", "warning", "any"]),
              default=None, help="Exit non-zero if findings at this severity or above")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def scan(
    skill_path: str,
    use_llm: bool,
    output_format: str,
    fail_on: str | None,
    output: str | None,
) -> None:
    """Deep security scan via SkillSpector (Pillar 2).

    Uses NVIDIA SkillSpector for 68-pattern deep scanning when available,
    otherwise falls back to skora's built-in security scanner.
    """
    from .integrations.skillspector import run_skillspector

    console.print(f"\n[bold]Deep security scan:[/bold] {skill_path}\n")

    report = run_skillspector(skill_path, use_llm=use_llm)

    if output_format == "json":
        payload = json.dumps(report.model_dump(), indent=2, default=str)
        click.echo(payload)
        if output:
            Path(output).write_text(payload)
    elif output_format == "sarif":
        console.print("[yellow]SARIF output requires skillspector directly.[/yellow]")
        console.print("[dim]Use: skillspector scan --format sarif <path>[/dim]")
    else:
        _display_security_report(report)
        if output:
            Path(output).write_text(
                json.dumps(report.model_dump(), indent=2, default=str)
            )
            console.print(f"\n[dim]Report exported to {output}[/dim]")

    if fail_on:
        if fail_on == "critical" and report.critical_count > 0:
            sys.exit(1)
        elif fail_on == "warning" and (report.critical_count + report.warning_count) > 0:
            sys.exit(1)
        elif fail_on == "any" and len(report.findings) > 0:
            sys.exit(1)


@main.command("metrics")
def list_metrics_cmd() -> None:
    """List all registered evaluation metrics."""
    from .api import list_metrics

    metrics = list_metrics()

    table = Table(title="Available Metrics")
    table.add_column("Name", style="cyan")
    table.add_column("Tier", justify="center")
    table.add_column("Description")

    tier_styles = {1: "[red]1[/red]", 2: "[yellow]2[/yellow]", 3: "[green]3[/green]"}

    for m in sorted(metrics, key=lambda x: (x["tier"], x["name"])):
        table.add_row(
            m["name"],
            tier_styles.get(m["tier"], str(m["tier"])),
            m["description"],
        )

    console.print(table)
    console.print(
        "\n[dim]Tiers: [red]1[/red]=Non-negotiable  "
        "[yellow]2[/yellow]=Diagnostic  "
        "[green]3[/green]=Efficiency[/dim]"
    )


def _display_quality_report(report) -> None:
    """Display a quality check report using Rich."""
    grade_colors = {
        "A+": "green bold", "A": "green", "B": "blue", "C": "yellow",
        "D": "red", "F": "red bold",
    }
    color = grade_colors.get(report.grade, "white")

    compliance = "[green]Yes[/green]" if report.spec_compliant else "[red]No[/red]"

    console.print(
        Panel(
            f"[bold]Skill:[/bold] {report.skill_name}\n"
            f"[bold]Grade:[/bold] [{color}]{report.grade}[/{color}]\n"
            f"[bold]Spec Compliant:[/bold] {compliance}\n"
            f"[bold]Errors:[/bold] {report.error_count}  "
            f"[bold]Warnings:[/bold] {report.warning_count}  "
            f"[bold]Info:[/bold] {report.info_count}\n"
            f"[bold]Tool:[/bold] {report.tool_used}",
            title="Quality Check Results",
        )
    )

    if report.violations:
        table = Table(title="Violations")
        table.add_column("Severity", style="bold")
        table.add_column("Rule")
        table.add_column("Message")
        table.add_column("File")
        table.add_column("Line", justify="right")
        table.add_column("Fixable", justify="center")

        severity_colors = {"critical": "red", "warning": "yellow", "info": "blue"}

        for v in report.violations:
            sev_color = severity_colors.get(v.severity.value, "white")
            table.add_row(
                f"[{sev_color}]{v.severity.value.upper()}[/{sev_color}]",
                v.rule_id,
                v.message,
                v.file_path or "-",
                str(v.line_number or "-"),
                "[green]Yes[/green]" if v.fixable else "[dim]No[/dim]",
            )

        console.print(table)
    else:
        console.print("[green]No quality violations found![/green]")


def _display_security_report(report) -> None:
    """Display a security report using Rich."""
    grade_colors = {"A": "green", "B": "blue", "C": "yellow", "D": "red", "F": "red bold"}
    color = grade_colors.get(report.grade, "white")

    console.print(
        Panel(
            f"[bold]Skill:[/bold] {report.skill_name}\n"
            f"[bold]Grade:[/bold] [{color}]{report.grade}[/{color}]\n"
            f"[bold]Score:[/bold] {report.score:.2f}/1.00\n"
            f"[bold]Critical:[/bold] {report.critical_count}  "
            f"[bold]Warnings:[/bold] {report.warning_count}  "
            f"[bold]Info:[/bold] {len(report.findings) - report.critical_count - report.warning_count}",
            title="Security Scan Results",
        )
    )

    if report.findings:
        table = Table(title="Findings")
        table.add_column("Severity", style="bold")
        table.add_column("Category")
        table.add_column("Description")
        table.add_column("Line", justify="right")
        table.add_column("Recommendation")

        severity_colors = {"critical": "red", "warning": "yellow", "info": "blue"}

        for f in report.findings:
            sev_color = severity_colors.get(f.severity.value, "white")
            table.add_row(
                f"[{sev_color}]{f.severity.value.upper()}[/{sev_color}]",
                f.category,
                f.description,
                str(f.line_number or "-"),
                f.recommendation,
            )

        console.print(table)
    else:
        console.print("[green]No security findings![/green]")


def _display_stats(stats: dict) -> None:
    """Display aggregate statistics."""
    if not stats or stats.get("total_evals", 0) == 0:
        return

    avg_score = stats.get("avg_score") or 0.0

    console.print(
        Panel(
            f"[bold]Total Evaluations:[/bold] {stats.get('total_evals', 0)}\n"
            f"[bold]Average Score:[/bold] {avg_score:.3f}\n"
            f"[bold]Passed:[/bold] [green]{stats.get('passed', 0)}[/green]  "
            f"[bold]Failed:[/bold] [red]{stats.get('failed', 0)}[/red]\n"
            f"[bold]Unique Skills:[/bold] {stats.get('unique_skills', 0)}",
            title="Evaluation Stats",
        )
    )


def _display_results_table(rows: list[dict]) -> None:
    """Display results in a table."""
    table = Table(title="Evaluation Results")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Skill", style="cyan")
    table.add_column("Verdict", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Timestamp", style="dim")

    verdict_colors = {"pass": "green", "fail": "red", "partial": "yellow"}

    for row in rows:
        v = row.get("verdict", "")
        v_color = verdict_colors.get(v, "white")
        table.add_row(
            row.get("id", "")[:8],
            row.get("skill_name", ""),
            f"[{v_color}]{v.upper()}[/{v_color}]",
            f"{row.get('overall_score', 0):.3f}",
            row.get("timestamp", "")[:19],
        )

    console.print(table)


if __name__ == "__main__":
    main()
