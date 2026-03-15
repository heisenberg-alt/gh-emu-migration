"""Report generation — Markdown + Rich console output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ._console import console
from .models import (
    AssessmentReport,
    MigrationPhase,
    MigrationPlan,
    Risk,
    Severity,
)

SEVERITY_COLORS = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "cyan",
    Severity.INFO: "dim",
}

SEVERITY_ICONS = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🔵",
    Severity.INFO: "⚪",
}

CHECK_ICONS = {True: "✅", False: "❌", None: "⬜"}


# ── Console rendering ──────────────────────────────────────────────

def print_assessment(report: AssessmentReport) -> None:
    """Render assessment report to the terminal."""
    console.rule("[bold]Migration Assessment Report[/]")
    console.print(f"Enterprise : [bold]{report.enterprise}[/]")
    console.print(f"Organization: [bold]{report.organization}[/]")
    console.print(f"Timestamp   : {report.timestamp}")
    console.print()

    # Summary table
    summary = Table(title="Organization Summary", show_lines=True)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")
    summary.add_row("Total members", str(report.total_members))
    summary.add_row("Total repositories", str(report.total_repos))
    summary.add_row("Outside collaborators", str(report.outside_collaborators))
    summary.add_row("SAML SSO configured", "Yes" if report.saml_configured else "No")
    console.print(summary)
    console.print()

    # Risks table
    _print_risks(report.risks)


def _print_risks(risks: list[Risk]) -> None:
    """Print risks grouped by phase."""
    for phase in MigrationPhase:
        phase_risks = [r for r in risks if r.phase == phase]
        if not phase_risks:
            continue

        table = Table(title=f"Risks — {phase.value.replace('_', ' ').title()}", show_lines=True)
        table.add_column("ID", width=8)
        table.add_column("Sev", width=4, justify="center")
        table.add_column("Check", width=5, justify="center")
        table.add_column("Title", min_width=30)
        table.add_column("Mitigation", min_width=40)

        for r in sorted(phase_risks, key=lambda x: list(Severity).index(x.severity)):
            table.add_row(
                r.id,
                SEVERITY_ICONS.get(r.severity, ""),
                CHECK_ICONS.get(r.check_passed, ""),
                f"[{SEVERITY_COLORS.get(r.severity, '')}]{r.title}[/]",
                r.mitigation[:120] + ("…" if len(r.mitigation) > 120 else ""),
            )
        console.print(table)
        console.print()


def print_plan(plan: MigrationPlan) -> None:
    """Render a migration plan to the terminal."""
    mode = "[bold yellow]DRY RUN[/]" if plan.dry_run else "[bold green]LIVE[/]"
    console.rule(f"[bold]Migration Plan[/]  ({mode})")
    console.print()

    for step in plan.steps:
        prefix = "🔧 MANUAL" if step.manual else "⚙️  AUTO"
        icon = {"pending": "⬜", "running": "🔄", "done": "✅",
                "skipped": "⏭️", "failed": "❌"}.get(step.status, "⬜")
        console.print(
            Panel(
                f"[dim]{prefix}[/]\n\n{step.description}",
                title=f"{icon} Step {step.order}: {step.title}",
                border_style="blue" if step.manual else "green",
                width=100,
            )
        )


# ── Markdown report generation ─────────────────────────────────────

def generate_markdown_report(
    report: AssessmentReport,
    sso_plan: MigrationPlan,
    emu_plan: MigrationPlan,
) -> str:
    """Generate a full Markdown migration report."""
    lines: list[str] = []
    _md = lines.append

    _md("# GitHub Enterprise Migration Report")
    _md(f"## ADFS → Entra ID SSO + EMU Migration")
    _md("")
    _md(f"- **Enterprise**: {report.enterprise}")
    _md(f"- **Organization**: {report.organization}")
    _md(f"- **Generated**: {report.timestamp}")
    _md(f"- **Members**: {report.total_members}")
    _md(f"- **Repositories**: {report.total_repos}")
    _md(f"- **Outside Collaborators**: {report.outside_collaborators}")
    _md(f"- **SAML SSO Configured**: {'Yes' if report.saml_configured else 'No'}")
    _md("")

    # ── Members ─────────────────────────────────────────────────────
    _md("## Organization Members")
    _md("")
    _md("| Login | Role | SAML Linked | Email |")
    _md("|-------|------|-------------|-------|")
    for m in report.members:
        saml = "✅" if m.saml_identity else "❌"
        login = m.login.replace("|", "\\|")
        email = (m.email or "—").replace("|", "\\|")
        _md(f"| {login} | {m.role} | {saml} | {email} |")
    _md("")

    # ── Risks ───────────────────────────────────────────────────────
    _md("## Risk Assessment")
    _md("")
    for phase in MigrationPhase:
        phase_risks = [r for r in report.risks if r.phase == phase]
        if not phase_risks:
            continue
        _md(f"### {phase.value.replace('_', ' ').title()}")
        _md("")
        for r in sorted(phase_risks, key=lambda x: list(Severity).index(x.severity)):
            icon = SEVERITY_ICONS.get(r.severity, "")
            check = CHECK_ICONS.get(r.check_passed, "")
            _md(f"#### {icon} [{r.id}] {r.title}  {check}")
            _md(f"**Severity**: {r.severity.value.upper()}")
            _md("")
            _md(r.description)
            _md("")
            _md(f"**Mitigation**: {r.mitigation}")
            _md("")

    # ── SSO Plan ────────────────────────────────────────────────────
    _md("## Phase 1: SAML SSO Switch (ADFS → Entra ID)")
    _md("")
    for step in sso_plan.steps:
        tag = "MANUAL" if step.manual else "AUTOMATED"
        _md(f"### Step {step.order}: {step.title}  `[{tag}]`")
        _md("")
        _md(step.description)
        _md("")

    # ── EMU Plan ────────────────────────────────────────────────────
    _md("## Phase 2: EMU Migration")
    _md("")
    for step in emu_plan.steps:
        tag = "MANUAL" if step.manual else "AUTOMATED"
        _md(f"### Step {step.order}: {step.title}  `[{tag}]`")
        _md("")
        _md(step.description)
        _md("")

    return "\n".join(lines)


def save_report(content: str, output_dir: str | Path, filename: str = "migration-report.md") -> Path:
    """Write the report to disk."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    path.write_text(content, encoding="utf-8")
    console.print(f"[green]Report saved to {path.resolve()}[/]")
    return path


def save_json_report(report: AssessmentReport, output_dir: str | Path) -> Path:
    """Write a JSON version of the assessment for programmatic consumption."""
    import dataclasses

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "assessment.json"

    def _ser(obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        if hasattr(obj, "value"):
            return obj.value
        raise TypeError(f"Cannot serialize {type(obj)}")

    path.write_text(
        json.dumps(dataclasses.asdict(report), indent=2, default=_ser),
        encoding="utf-8",
    )
    console.print(f"[green]JSON report saved to {path.resolve()}[/]")
    return path
