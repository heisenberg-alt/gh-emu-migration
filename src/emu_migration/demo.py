"""Offline demo with synthetic data — no GitHub credentials needed."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from .assessment import STATIC_RISKS, _run_automated_checks
from .emu_migration import build_emu_migration_plan
from .models import AssessmentReport, OrgMember, RepoInfo
from .report import (
    console,
    generate_markdown_report,
    print_assessment,
    print_plan,
    save_report,
)
from .sso_migration import build_sso_switch_plan

DEMO_CONFIG = {
    "github": {
        "enterprise": "contoso-enterprise",
        "organization": "contoso-dev",
        "token": "demo-token-not-used",
    },
    "entra_id": {
        "tenant_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "client_id": "11111111-2222-3333-4444-555555555555",
        "client_secret": "demo",
        "app_display_name": "GitHub Enterprise Managed User",
    },
    "adfs": {
        "entity_id": "https://adfs.contoso.com/adfs/services/trust",
        "sso_url": "https://adfs.contoso.com/adfs/ls/",
    },
    "emu": {
        "short_code": "contoso",
        "owners_group": "GitHub-Org-Owners",
        "members_group": "GitHub-Org-Members",
    },
    "migration": {
        "dry_run": True,
        "report_output": "reports/",
    },
}


def _build_demo_report() -> AssessmentReport:
    """Create a synthetic assessment report for demo purposes."""
    members = [
        OrgMember(login="jdoe", github_id=1001, email="jdoe@contoso.com",
                  name="Jane Doe", role="admin", saml_identity="jdoe@contoso.com"),
        OrgMember(login="bsmith", github_id=1002, email="bsmith@contoso.com",
                  name="Bob Smith", role="member", saml_identity="bsmith@contoso.com"),
        OrgMember(login="agarcia", github_id=1003, email="agarcia@contoso.com",
                  name="Ana Garcia", role="member", saml_identity="agarcia@contoso.com"),
        OrgMember(login="tchen", github_id=1004, email="tchen@contoso.com",
                  name="Tina Chen", role="member", saml_identity=None),  # not linked!
        OrgMember(login="svc-ci-bot", github_id=1005, email="ci@contoso.com",
                  name="CI Bot", role="member", saml_identity="svc-ci@contoso.com"),
        OrgMember(login="mjohnson", github_id=1006, email="mjohnson@contoso.com",
                  name="Mike Johnson", role="member", saml_identity="mjohnson@contoso.com"),
    ]

    repos = [
        RepoInfo(name="backend-api", full_name="contoso-dev/backend-api",
                 private=True, fork=False, archived=False, size_kb=45000,
                 default_branch="main", has_actions=True),
        RepoInfo(name="frontend-app", full_name="contoso-dev/frontend-app",
                 private=True, fork=False, archived=False, size_kb=32000,
                 default_branch="main", has_actions=True),
        RepoInfo(name="shared-libs", full_name="contoso-dev/shared-libs",
                 private=True, fork=False, archived=False, size_kb=8000,
                 default_branch="main", has_actions=True),
        RepoInfo(name="docs", full_name="contoso-dev/docs",
                 private=False, fork=False, archived=False, size_kb=2000,
                 default_branch="main", has_actions=False),
        RepoInfo(name="legacy-monolith", full_name="contoso-dev/legacy-monolith",
                 private=True, fork=False, archived=True, size_kb=120000,
                 default_branch="master", has_actions=False),
        RepoInfo(name="infra-terraform", full_name="contoso-dev/infra-terraform",
                 private=True, fork=False, archived=False, size_kb=5000,
                 default_branch="main", has_actions=True),
    ]

    # Clone static risks and run checks against demo data
    risks = [copy.copy(r) for r in STATIC_RISKS]

    report = AssessmentReport(
        enterprise="contoso-enterprise",
        organization="contoso-dev",
        timestamp=datetime.now(timezone.utc).isoformat(),
        members=members,
        repos=repos,
        risks=risks,
        total_members=len(members),
        total_repos=len(repos),
        outside_collaborators=2,
        saml_configured=True,
    )

    _run_automated_checks(report, DEMO_CONFIG)
    return report


def run_demo() -> None:
    """Execute the full demo flow."""
    console.print("[bold magenta]═══ DEMO MODE ═══[/]")
    console.print("Using synthetic data — no GitHub connection required.\n")

    # 1. Assessment
    report = _build_demo_report()
    print_assessment(report)

    # 2. SSO plan
    sso_plan = build_sso_switch_plan(DEMO_CONFIG)
    print_plan(sso_plan)

    # 3. EMU plan
    emu_plan = build_emu_migration_plan(DEMO_CONFIG)
    print_plan(emu_plan)

    # 4. Save report
    md = generate_markdown_report(report, sso_plan, emu_plan)
    save_report(md, "reports/", "demo-migration-report.md")

    console.print("\n[bold green]Demo complete![/] Check reports/demo-migration-report.md")
