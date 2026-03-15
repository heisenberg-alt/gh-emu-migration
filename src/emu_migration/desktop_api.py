"""Python API exposed to the pywebview JS frontend.

Every public method on ``DesktopAPI`` is callable from JS as:
    window.pywebview.api.<method_name>(args…)

All methods return plain JSON-serialisable dicts/lists so pywebview
can marshal them across the bridge automatically.
"""

from __future__ import annotations

import logging

from .assessment import run_assessment
from .config import _validate_required
from .demo import DEMO_CONFIG, _build_demo_report
from .emu_migration import (
    build_emu_migration_plan,
    generate_gei_script,
    generate_mannequin_mapping,
)
from .gei import GEIClient
from .models import AssessmentReport
from .report import CHECK_ICONS, SEVERITY_ICONS, generate_markdown_report
from .sso_migration import build_sso_switch_plan, validate_sso_readiness

logger = logging.getLogger(__name__)


# ── Serialisers ──────────────────────────────────────────────────────

def _serialise_report(report: AssessmentReport) -> dict:
    return {
        "enterprise": report.enterprise,
        "organization": report.organization,
        "timestamp": report.timestamp,
        "total_members": report.total_members,
        "total_repos": report.total_repos,
        "outside_collaborators": report.outside_collaborators,
        "saml_configured": report.saml_configured,
        "emu_ready": report.emu_ready,
        "members": [
            {
                "login": m.login,
                "role": m.role,
                "email": m.email,
                "saml_identity": m.saml_identity,
            }
            for m in report.members
        ],
        "repos": [
            {
                "name": r.name,
                "private": r.private,
                "archived": r.archived,
                "size_kb": r.size_kb,
                "has_actions": r.has_actions,
                "default_branch": r.default_branch,
            }
            for r in report.repos
        ],
        "risks": [
            {
                "id": r.id,
                "phase": r.phase.value,
                "severity": r.severity.value,
                "title": r.title,
                "description": r.description,
                "mitigation": r.mitigation,
                "check_passed": r.check_passed,
                "sev_icon": SEVERITY_ICONS.get(r.severity, ""),
                "check_icon": CHECK_ICONS.get(r.check_passed, ""),
            }
            for r in report.risks
        ],
    }


def _serialise_plan(plan) -> dict:
    return {
        "steps": [
            {
                "order": s.order,
                "phase": s.phase.value,
                "title": s.title,
                "description": s.description,
                "manual": s.manual,
            }
            for s in plan.steps
        ],
    }


# ── Desktop API class ────────────────────────────────────────────────

class DesktopAPI:
    """Exposed to the webview JS context via ``window.pywebview.api``."""

    # ── Demo ──────────────────────────────────────────────────────

    def demo(self) -> dict:
        """Return full demo assessment with synthetic data."""
        report = _build_demo_report()
        sso_plan = build_sso_switch_plan(DEMO_CONFIG)
        emu_plan = build_emu_migration_plan(DEMO_CONFIG)
        md = generate_markdown_report(report, sso_plan, emu_plan)
        repos = [r.name for r in report.repos]
        gei_script = generate_gei_script(
            repos, report.organization, report.organization + "-emu",
        )
        return {
            "report": _serialise_report(report),
            "sso_plan": _serialise_plan(sso_plan),
            "emu_plan": _serialise_plan(emu_plan),
            "markdown": md,
            "gei_script": gei_script,
        }

    # ── Live assessment ───────────────────────────────────────────

    def assess(self, config: dict) -> dict:
        """Run a live assessment against GitHub."""
        try:
            _validate_required(config)
            report = run_assessment(config)
            return {"ok": True, "report": _serialise_report(report)}
        except (ValueError, KeyError) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("Assessment failed")
            return {"ok": False, "error": f"Assessment failed: {type(exc).__name__}"}

    # ── Migration plans ───────────────────────────────────────────

    def plans(self, config: dict) -> dict:
        """Generate SSO + EMU migration plans."""
        try:
            _validate_required(config)
        except ValueError as exc:
            return {"sso_readiness_issues": [str(exc)], "sso_plan": {"steps": []}, "emu_plan": {"steps": []}}
        issues = validate_sso_readiness(config)
        sso_plan = build_sso_switch_plan(config)
        emu_plan = build_emu_migration_plan(config)
        return {
            "sso_readiness_issues": issues,
            "sso_plan": _serialise_plan(sso_plan),
            "emu_plan": _serialise_plan(emu_plan),
        }

    # ── Full markdown report ──────────────────────────────────────

    def report(self, config: dict) -> dict:
        """Generate the full Markdown report."""
        try:
            _validate_required(config)
            report = run_assessment(config)
            sso_plan = build_sso_switch_plan(config)
            emu_plan = build_emu_migration_plan(config)
            md = generate_markdown_report(report, sso_plan, emu_plan)
            return {"ok": True, "markdown": md, "report": _serialise_report(report)}
        except (ValueError, KeyError) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("Report generation failed")
            return {"ok": False, "error": f"Report failed: {type(exc).__name__}"}

    # ── GEI script generation ─────────────────────────────────────

    def gei_script(self, repos: list[str], source_org: str, target_org: str) -> dict:
        """Generate a GEI migration shell script."""
        script = generate_gei_script(repos, source_org, target_org)
        return {"script": script}

    # ── GEI execution (desktop-only capability) ───────────────────

    def check_gei(self) -> dict:
        """Check if gh CLI and gh-gei extension are installed."""
        return {"installed": GEIClient.is_installed()}

    def run_gei_migration(
        self,
        source_org: str,
        target_org: str,
        repos: list[str],
        source_pat: str,
        target_pat: str,
        dry_run: bool = True,
    ) -> dict:
        """Execute GEI migration from the desktop (no server needed)."""
        try:
            client = GEIClient(source_pat=source_pat, target_pat=target_pat)
            client.ensure_extension()
            run = client.migrate_repos(source_org, target_org, repos, dry_run=dry_run)
            return {
                "ok": True,
                "succeeded": run.succeeded,
                "failed": run.failed,
                "total": run.total,
                "results": [
                    {
                        "repo": r.repo,
                        "status": r.status.value,
                        "migration_id": r.migration_id,
                        "error": r.error,
                    }
                    for r in run.results
                ],
            }
        except Exception as exc:
            logger.exception("GEI migration failed")
            return {"ok": False, "error": str(exc)}

    # ── Mannequin mapping ─────────────────────────────────────────

    def mannequin_mapping(self, logins: list[str], short_code: str = "company") -> dict:
        """Generate mannequin identity mappings."""
        members_raw = [{"login": login} for login in logins]
        mappings = generate_mannequin_mapping(members_raw, short_code)
        return {"mappings": mappings}
