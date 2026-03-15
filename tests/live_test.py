"""End-to-end live test runner.

Runs the assessment, plan generation, and report against a real GitHub org.
Validates that each stage produces correct output.

Usage:
  python -m tests.live_test --config config.yaml
  python -m tests.live_test --config config.yaml --full
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from rich.panel import Panel

from emu_migration._console import console
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_live_test(config_path: str, full: bool = False) -> bool:
    """Execute live tests against a real GitHub org."""
    from emu_migration.config import load_config
    from emu_migration.assessment import run_assessment
    from emu_migration.sso_migration import build_sso_switch_plan, validate_sso_readiness
    from emu_migration.emu_migration import build_emu_migration_plan, generate_gei_script
    from emu_migration.report import (
        print_assessment,
        print_plan,
        generate_markdown_report,
        save_report,
        save_json_report,
    )

    results: dict[str, bool] = {}
    start = time.time()

    # ── 1. Config loading ───────────────────────────────────────────
    console.rule("[bold]Test 1: Configuration Loading")
    try:
        cfg = load_config(config_path)
        console.print("[green]✅ Config loaded[/]")
        console.print(f"   Enterprise: {cfg['github']['enterprise']}")
        console.print(f"   Org       : {cfg['github']['organization']}")
        console.print(f"   Tenant    : {cfg['entra_id']['tenant_id']}")
        results["config_load"] = True
    except Exception as e:
        console.print(f"[red]❌ Config failed: {e}[/]")
        results["config_load"] = False
        return False

    # ── 2. Assessment ───────────────────────────────────────────────
    console.rule("[bold]Test 2: Live Assessment")
    try:
        report = run_assessment(cfg)

        checks = {
            "has_members": report.total_members > 0,
            "has_repos": report.total_repos > 0,
            "has_risks": len(report.risks) > 0,
            "has_timestamp": bool(report.timestamp),
            "enterprise_set": report.enterprise == cfg["github"]["enterprise"],
            "org_set": report.organization == cfg["github"]["organization"],
        }

        for check_name, passed in checks.items():
            icon = "✅" if passed else "❌"
            console.print(f"   {icon} {check_name}")

        results["assessment"] = all(checks.values())

        console.print(f"\n   Members: {report.total_members}")
        console.print(f"   Repos  : {report.total_repos}")
        console.print(f"   Outside: {report.outside_collaborators}")
        console.print(f"   SAML   : {report.saml_configured}")
        console.print(f"   Risks  : {len(report.risks)}")

        # Print full assessment
        console.print()
        print_assessment(report)

    except Exception as e:
        console.print(f"[red]❌ Assessment failed: {e}[/]")
        results["assessment"] = False
        report = None

    # ── 3. SSO readiness ────────────────────────────────────────────
    console.rule("[bold]Test 3: SSO Readiness Check")
    try:
        issues = validate_sso_readiness(cfg)
        if issues:
            console.print("[yellow]Warnings:[/]")
            for issue in issues:
                console.print(f"   ⚠ {issue}")
        else:
            console.print("[green]✅ No SSO readiness issues[/]")
        results["sso_readiness"] = True  # check itself succeeds even with warnings
    except Exception as e:
        console.print(f"[red]❌ SSO readiness check failed: {e}[/]")
        results["sso_readiness"] = False

    # ── 4. SSO plan ─────────────────────────────────────────────────
    console.rule("[bold]Test 4: SSO Migration Plan")
    try:
        sso_plan = build_sso_switch_plan(cfg)
        console.print(f"[green]✅ SSO plan generated: {len(sso_plan.steps)} steps[/]")
        assert len(sso_plan.steps) == 10, f"Expected 10 steps, got {len(sso_plan.steps)}"
        print_plan(sso_plan)
        results["sso_plan"] = True
    except Exception as e:
        console.print(f"[red]❌ SSO plan failed: {e}[/]")
        results["sso_plan"] = False
        sso_plan = None

    # ── 5. EMU plan ─────────────────────────────────────────────────
    console.rule("[bold]Test 5: EMU Migration Plan")
    try:
        emu_plan = build_emu_migration_plan(cfg)
        console.print(f"[green]✅ EMU plan generated: {len(emu_plan.steps)} steps[/]")
        assert len(emu_plan.steps) == 14, f"Expected 14 steps, got {len(emu_plan.steps)}"
        print_plan(emu_plan)
        results["emu_plan"] = True
    except Exception as e:
        console.print(f"[red]❌ EMU plan failed: {e}[/]")
        results["emu_plan"] = False
        emu_plan = None

    # ── 6. Report generation ────────────────────────────────────────
    console.rule("[bold]Test 6: Report Generation")
    try:
        if report and sso_plan and emu_plan:
            md = generate_markdown_report(report, sso_plan, emu_plan)
            output_dir = cfg.get("migration", {}).get("report_output", "reports/")

            md_path = save_report(md, output_dir, "live-test-report.md")
            json_path = save_json_report(report, output_dir)

            assert md_path.exists(), "Markdown report not written"
            assert json_path.exists(), "JSON report not written"
            assert md_path.stat().st_size > 1000, "Report too small"

            console.print("[green]✅ Reports generated[/]")
            console.print(f"   Markdown: {md_path} ({md_path.stat().st_size:,} bytes)")
            console.print(f"   JSON    : {json_path} ({json_path.stat().st_size:,} bytes)")
            results["report"] = True
        else:
            console.print("[yellow]⏭️  Skipped (missing prerequisites)[/]")
            results["report"] = False
    except Exception as e:
        console.print(f"[red]❌ Report generation failed: {e}[/]")
        results["report"] = False

    # ── 7. GEI script (only in full mode) ───────────────────────────
    if full:
        console.rule("[bold]Test 7: GEI Script Generation")
        try:
            if report:
                repo_names = [r.name for r in report.repos if not r.archived]
                org = cfg["github"]["organization"]
                target_org = f"{org}-emu"
                script = generate_gei_script(repo_names, org, target_org)

                output_dir = Path(cfg.get("migration", {}).get("report_output", "reports/"))
                output_dir.mkdir(parents=True, exist_ok=True)
                script_path = output_dir / "live-test-migrate.sh"
                script_path.write_text(script, encoding="utf-8")

                assert "gh gei migrate-repo" in script, "Script missing GEI commands"
                console.print(f"[green]✅ GEI script generated: {script_path}[/]")
                console.print(f"   Repos to migrate: {len(repo_names)}")
                results["gei_script"] = True
            else:
                results["gei_script"] = False
        except Exception as e:
            console.print(f"[red]❌ GEI script failed: {e}[/]")
            results["gei_script"] = False

    # ── Summary ─────────────────────────────────────────────────────
    elapsed = time.time() - start
    console.print()
    console.rule("[bold]Test Summary")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, ok in results.items():
        icon = "✅" if ok else "❌"
        console.print(f"  {icon} {name}")

    color = "green" if passed == total else "yellow" if passed > total // 2 else "red"
    console.print(
        Panel(
            f"[{color}]{passed}/{total} tests passed[/] in {elapsed:.1f}s",
            title="Result",
            border_style=color,
        )
    )

    return passed == total


def main():
    parser = argparse.ArgumentParser(description="Run live tests against a real GitHub org")
    parser.add_argument("--config", "-c", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--full", action="store_true", help="Run full test suite including GEI script")

    args = parser.parse_args()

    success = run_live_test(args.config, full=args.full)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
