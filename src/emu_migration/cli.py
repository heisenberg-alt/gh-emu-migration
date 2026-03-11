"""CLI entry point for the GitHub EMU Migration POC."""

from __future__ import annotations

import logging
import os
import sys

# Ensure UTF-8 output on Windows so Rich emoji/box-drawing work
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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


# ── setup-test-org ──────────────────────────────────────────────────

@main.command("setup-test-org")
@click.option("--org", required=True, help="GitHub organization slug")
@click.option("--token", required=True, help="GitHub PAT (admin:org, repo, workflow)")
@click.option("--invite", multiple=True, help="GitHub usernames to invite (repeat for multiple)")
@click.option("--collaborator", default=None, help="Username to add as outside collaborator")
@click.option("--cleanup", is_flag=True, help="Delete test-* repos instead of creating")
def setup_test_org(org: str, token: str, invite: tuple, collaborator: str | None, cleanup: bool) -> None:
    """Provision a demo GitHub org with test repos and users.

    Creates 5 test repositories, adds Actions workflows, invites members,
    and optionally adds outside collaborators — everything needed to
    run a realistic assessment.
    """
    from tests.setup_test_org import GitHubSetup
    setup = GitHubSetup(token=token, org=org)
    if cleanup:
        console.print(f"[bold yellow]Cleaning up test repos in {org}…[/]")
        setup.cleanup_test_repos()
    else:
        setup.full_setup(
            invite_users=list(invite) or None,
            collaborator_user=collaborator,
        )


# ── check-entra ─────────────────────────────────────────────────────

@main.command("check-entra")
@click.option("--tenant-id", required=True, help="Entra ID tenant ID")
@click.option("--org", required=True, help="GitHub organization slug")
def check_entra(tenant_id: str, org: str) -> None:
    """Check Entra ID readiness for GitHub SAML SSO.

    Verifies Azure CLI login, queries existing Enterprise Apps and
    security groups. Requires: az login first.
    """
    from tests.setup_entra_id import check_entra_readiness
    check_entra_readiness(tenant_id, org)


# ── setup-entra ──────────────────────────────────────────────────────

@main.command("setup-entra")
@click.option("--tenant-id", required=True, help="Entra ID tenant ID")
@click.option("--org", required=True, help="GitHub organization slug")
@click.option("--enterprise", default="", help="GitHub enterprise slug (for EMU SCIM)")
def setup_entra(tenant_id: str, org: str, enterprise: str) -> None:
    """Create Entra ID Enterprise App and security groups for GitHub SSO.

    Automates: App Registration, Service Principal, and security group
    creation. Prints remaining manual steps for SAML config.
    Requires: az login first.
    """
    from tests.setup_entra_id import setup_entra_for_github
    setup_entra_for_github(tenant_id, org, enterprise)


# ── live-test ────────────────────────────────────────────────────────

@main.command("live-test")
@click.option("--full", is_flag=True, help="Run full suite including GEI script gen")
@click.pass_context
def live_test(ctx: click.Context, full: bool) -> None:
    """Run end-to-end live tests against a real GitHub org.

    Validates assessment, plan generation, and report output.
    Requires a valid config.yaml with real credentials.
    """
    from tests.live_test import run_live_test
    success = run_live_test(ctx.obj["config_path"], full=full)
    sys.exit(0 if success else 1)


# ── Helpers ─────────────────────────────────────────────────────────

def _load_cfg(ctx: click.Context) -> dict:
    try:
        return load_config(ctx.obj["config_path"])
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Configuration error:[/] {exc}")
        sys.exit(1)
