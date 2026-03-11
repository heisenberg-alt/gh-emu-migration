"""CLI entry point for the GitHub EMU Migration POC."""

from __future__ import annotations

import logging
import sys

import click
from rich.console import Console

from .assessment import run_assessment
from .config import load_config
from .emu_migration import build_emu_migration_plan, generate_gei_script
from .report import (
    generate_markdown_report,
    print_assessment,
    print_plan,
    save_json_report,
    save_report,
)
from .sso_migration import build_sso_switch_plan, validate_sso_readiness

console = Console()
logger = logging.getLogger("emu_migration")


@click.group()
@click.option("--config", "-c", default="config.yaml", help="Path to config.yaml")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def main(ctx: click.Context, config: str, verbose: bool) -> None:
    """GitHub Enterprise ADFS → Entra ID SSO + EMU Migration Tool."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


# ── assess ──────────────────────────────────────────────────────────

@main.command()
@click.pass_context
def assess(ctx: click.Context) -> None:
    """Run a full pre-migration assessment.

    Connects to GitHub, inventories members/repos, evaluates risks,
    and prints a summary to the terminal.
    """
    cfg = _load_cfg(ctx)
    console.print("[bold]Running pre-migration assessment …[/]\n")

    report = run_assessment(cfg)
    print_assessment(report)

    output_dir = cfg.get("migration", {}).get("report_output", "reports/")
    save_json_report(report, output_dir)


# ── plan ────────────────────────────────────────────────────────────

@main.command()
@click.option("--phase", type=click.Choice(["sso", "emu", "all"]), default="all")
@click.pass_context
def plan(ctx: click.Context, phase: str) -> None:
    """Generate and display the migration plan.

    Shows step-by-step instructions for SSO switch and/or EMU migration.
    """
    cfg = _load_cfg(ctx)

    if phase in ("sso", "all"):
        console.print("[bold]Validating SSO switch readiness …[/]\n")
        issues = validate_sso_readiness(cfg)
        if issues:
            console.print("[yellow]SSO readiness warnings:[/]")
            for issue in issues:
                console.print(f"  ⚠ {issue}")
            console.print()

        sso_plan = build_sso_switch_plan(cfg)
        print_plan(sso_plan)

    if phase in ("emu", "all"):
        emu_plan = build_emu_migration_plan(cfg)
        print_plan(emu_plan)


# ── report ──────────────────────────────────────────────────────────

@main.command()
@click.pass_context
def report(ctx: click.Context) -> None:
    """Generate a full Markdown migration report.

    Runs assessment + builds both plans, then writes a combined
    Markdown report to the configured output directory.
    """
    cfg = _load_cfg(ctx)

    console.print("[bold]Running assessment …[/]")
    assessment = run_assessment(cfg)

    console.print("[bold]Building migration plans …[/]")
    sso_plan = build_sso_switch_plan(cfg)
    emu_plan = build_emu_migration_plan(cfg)

    md = generate_markdown_report(assessment, sso_plan, emu_plan)
    output_dir = cfg.get("migration", {}).get("report_output", "reports/")
    save_report(md, output_dir)
    save_json_report(assessment, output_dir)

    console.print("\n[bold green]Done![/] Review the report in the reports/ folder.")


# ── generate-gei-script ────────────────────────────────────────────

@main.command("generate-gei-script")
@click.pass_context
def generate_gei(ctx: click.Context) -> None:
    """Generate a GEI (GitHub Enterprise Importer) migration script.

    Fetches the repo list from the source org and creates a bash script
    with one `gh gei migrate-repo` command per repository.
    """
    cfg = _load_cfg(ctx)
    from .github_client import GitHubClient

    gh = GitHubClient(token=cfg["github"]["token"])
    org = cfg["github"]["organization"]
    target_org = f"{org}-emu"
    short_code = cfg.get("emu", {}).get("short_code", "company")

    console.print(f"[bold]Fetching repos from {org} …[/]")
    repos = gh.get_org_repos(org)
    repo_names = [r["name"] for r in repos if not r.get("archived")]
    console.print(f"Found {len(repo_names)} active repositories.")

    script = generate_gei_script(repo_names, org, target_org)
    from pathlib import Path
    output_dir = Path(cfg.get("migration", {}).get("report_output", "reports/"))
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = output_dir / "migrate-repos.sh"
    script_path.write_text(script, encoding="utf-8")
    console.print(f"[green]GEI script saved to {script_path.resolve()}[/]")


# ── dry-run (offline demo) ─────────────────────────────────────────

@main.command("demo")
def demo() -> None:
    """Run an offline demo with sample data (no GitHub connection needed).

    Useful for evaluating the tool's output format before configuring
    real credentials.
    """
    from .demo import run_demo
    run_demo()


# ── Helpers ─────────────────────────────────────────────────────────

def _load_cfg(ctx: click.Context) -> dict:
    try:
        return load_config(ctx.obj["config_path"])
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Configuration error:[/] {exc}")
        sys.exit(1)
