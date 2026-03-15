"""Risk assessment engine for ADFS → Entra ID + EMU migration."""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any

from ._console import console
from .github_client import GitHubClient
from .models import (
    AssessmentReport,
    MigrationPhase,
    OrgMember,
    RepoInfo,
    Risk,
    Severity,
)

logger = logging.getLogger(__name__)


# ── Static risk catalogue ──────────────────────────────────────────

STATIC_RISKS: list[Risk] = [
    # ── SSO switch risks ──
    Risk(
        id="SSO-001",
        phase=MigrationPhase.SSO_SWITCH,
        severity=Severity.CRITICAL,
        title="SSO downtime during IdP switch",
        description=(
            "Changing the SAML IdP from ADFS to Entra ID requires updating the "
            "SSO configuration on the GitHub Enterprise organization settings page. "
            "During this window members cannot authenticate via SSO."
        ),
        mitigation=(
            "Schedule the cut-over during a maintenance window. "
            "Pre-configure the Entra ID Enterprise App and test with a staging org first. "
            "Keep ADFS running as fallback until validation completes."
        ),
    ),
    Risk(
        id="SSO-002",
        phase=MigrationPhase.SSO_SWITCH,
        severity=Severity.HIGH,
        title="SAML NameID mismatch between ADFS and Entra ID",
        description=(
            "ADFS may use a different NameID format (e.g. Windows domain\\user) "
            "than Entra ID (typically UPN or email). A mismatch breaks existing "
            "SAML identity linkages; users must re-authenticate and re-link."
        ),
        mitigation=(
            "Audit current ADFS NameID claim rules. Configure the Entra ID "
            "Enterprise App to emit the exact same NameID format and value. "
            "If that's not possible, plan for a re-link step for all users."
        ),
        automated_check=True,
    ),
    Risk(
        id="SSO-003",
        phase=MigrationPhase.SSO_SWITCH,
        severity=Severity.MEDIUM,
        title="Conditional Access policies may block GitHub SSO",
        description=(
            "Entra ID Conditional Access policies (MFA, device compliance, "
            "IP restrictions) could prevent users from completing SAML sign-in "
            "to GitHub if not properly scoped."
        ),
        mitigation=(
            "Review Conditional Access policies applied to the GitHub Enterprise "
            "App in Entra ID. Create exceptions or targeted policies as needed."
        ),
    ),
    Risk(
        id="SSO-004",
        phase=MigrationPhase.SSO_SWITCH,
        severity=Severity.MEDIUM,
        title="Service accounts relying on ADFS tokens",
        description=(
            "CI/CD pipelines or automation that authenticates through ADFS-based "
            "SAML may break when the IdP changes."
        ),
        mitigation=(
            "Inventory all service accounts and PATs. Service accounts should "
            "use GitHub Apps or fine-grained PATs that don't require SSO. "
            "Authorize them after the new SSO config is active."
        ),
        automated_check=True,
    ),
    # ── EMU migration risks ──
    Risk(
        id="EMU-001",
        phase=MigrationPhase.EMU_MIGRATION,
        severity=Severity.CRITICAL,
        title="Personal accounts cannot be converted to EMU in-place",
        description=(
            "GitHub EMU accounts are distinct from personal accounts. There is "
            "no automated path to convert a personal account into a managed one. "
            "Users must be provisioned as new EMU accounts (login_shortcode) and "
            "repo access must be re-granted."
        ),
        mitigation=(
            "Create a new EMU-enabled enterprise. Provision users via SCIM from "
            "Entra ID. Use GitHub's Enterprise migration tooling (GEI) to transfer "
            "repositories. Users will have new @_shortcode logins."
        ),
    ),
    Risk(
        id="EMU-002",
        phase=MigrationPhase.EMU_MIGRATION,
        severity=Severity.CRITICAL,
        title="Contribution history is tied to personal accounts",
        description=(
            "Commits, issues, PRs, and reviews authored by personal accounts will "
            "show as authored by those personal accounts (now external to the org). "
            "EMU accounts are separate identities."
        ),
        mitigation=(
            "Use mannequin reclaim (Enterprise Importer) to map old identities "
            "to new EMU accounts after repo migration. Communicate to users that "
            "their profile contribution graphs will reset on the EMU account."
        ),
    ),
    Risk(
        id="EMU-003",
        phase=MigrationPhase.EMU_MIGRATION,
        severity=Severity.HIGH,
        title="Outside collaborators are not supported in EMU",
        description=(
            "EMU organizations do not allow outside collaborators. External "
            "contributors with access to private repos lose access."
        ),
        mitigation=(
            "Audit outside collaborators. Move shared repos to a non-EMU org, "
            "use GitHub's repository forking, or convert collaborators to guest "
            "accounts if Entra B2B is available."
        ),
        automated_check=True,
    ),
    Risk(
        id="EMU-004",
        phase=MigrationPhase.EMU_MIGRATION,
        severity=Severity.HIGH,
        title="Personal forks, stars, and gists are lost",
        description=(
            "EMU accounts cannot fork to personal namespaces or retain stars/gists "
            "from the old personal account."
        ),
        mitigation=(
            "Notify users in advance. Provide a script for users to export their "
            "gists and starred repos list before migration."
        ),
    ),
    Risk(
        id="EMU-005",
        phase=MigrationPhase.EMU_MIGRATION,
        severity=Severity.HIGH,
        title="GitHub Actions secrets and environments need reconfiguration",
        description=(
            "Organization and repo-level Actions secrets, environments, and OIDC "
            "trust policies reference the old org/enterprise. After migration they "
            "must be recreated."
        ),
        mitigation=(
            "Export all secrets metadata (not values) before migration. Document "
            "each repo's Actions configuration. Re-create secrets in the new EMU org."
        ),
        automated_check=True,
    ),
    Risk(
        id="EMU-006",
        phase=MigrationPhase.EMU_MIGRATION,
        severity=Severity.MEDIUM,
        title="GitHub Packages may need re-publishing",
        description=(
            "Packages published under the old org namespace won't transfer "
            "automatically if the org slug changes."
        ),
        mitigation=(
            "Keep the same org slug when possible. If the slug changes, re-publish "
            "critical packages under the new namespace and update downstream references."
        ),
        automated_check=True,
    ),
    Risk(
        id="EMU-007",
        phase=MigrationPhase.EMU_MIGRATION,
        severity=Severity.MEDIUM,
        title="SCIM provisioning errors may orphan accounts",
        description=(
            "If SCIM provisioning from Entra ID fails for some users, they won't "
            "have EMU accounts and can't access the new org."
        ),
        mitigation=(
            "Test SCIM provisioning thoroughly with a small pilot group. Monitor "
            "the Entra ID provisioning logs. Have a rollback plan."
        ),
    ),
    # ── Validation risks ──
    Risk(
        id="VAL-001",
        phase=MigrationPhase.VALIDATION,
        severity=Severity.HIGH,
        title="PATs and SSH keys need SSO authorization",
        description=(
            "After enabling SSO with a new IdP, all PATs and SSH keys must be "
            "re-authorized for SSO. Until then, API/git operations fail."
        ),
        mitigation=(
            "Communicate to all users before migration. Provide step-by-step "
            "instructions for authorizing tokens/keys for the new SSO config."
        ),
    ),
    Risk(
        id="VAL-002",
        phase=MigrationPhase.VALIDATION,
        severity=Severity.MEDIUM,
        title="GitHub Apps and OAuth Apps need re-approval",
        description=(
            "Third-party and internal GitHub/OAuth Apps may need to be "
            "re-approved under the org's new SSO policy."
        ),
        mitigation=(
            "List all installed GitHub Apps and OAuth App grants before migration. "
            "Re-approve them in the new org after migration."
        ),
        automated_check=True,
    ),
]


# ── Dynamic assessment ─────────────────────────────────────────────

def run_assessment(cfg: dict[str, Any]) -> AssessmentReport:
    """Connect to GitHub, collect org data, and evaluate risks."""
    gh = GitHubClient(token=cfg["github"]["token"])
    org_slug = cfg["github"]["organization"]
    ent_slug = cfg["github"]["enterprise"]
    short_code = cfg.get("emu", {}).get("short_code", "company")

    report = AssessmentReport(
        enterprise=ent_slug,
        organization=org_slug,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # ── Collect members ─────────────────────────────────────────────
    logger.info("Fetching org members for %s …", org_slug)
    try:
        raw_members = gh.get_org_members(org_slug)
        for m in raw_members:
            member = OrgMember(
                login=m["login"],
                github_id=m["id"],
                name=m.get("name"),
                email=m.get("email"),
            )
            # Fetch role
            try:
                detail = gh.get_org_member_detail(org_slug, m["login"])
                member.role = detail.get("role", "member")
            except Exception:
                pass
            report.members.append(member)
        report.total_members = len(report.members)
        logger.info("Found %d members", report.total_members)
    except Exception as exc:
        logger.error("Failed to fetch members: %s", exc)
        console.print(f"[yellow]Warning: failed to fetch org members — {exc}[/]")

    # ── Collect SAML identities ─────────────────────────────────────
    logger.info("Fetching SAML identities …")
    try:
        saml_edges = gh.get_saml_identities(org_slug)
        saml_map: dict[str, str] = {}
        for node in saml_edges:
            user = node.get("user")
            saml_id = node.get("samlIdentity", {}).get("nameId", "")
            if user:
                saml_map[user["login"]] = saml_id
        for member in report.members:
            member.saml_identity = saml_map.get(member.login)
        if saml_map:
            report.saml_configured = True
        logger.info("SAML configured: %s (%d linked identities)",
                     report.saml_configured, len(saml_map))
    except Exception as exc:
        logger.warning("Could not fetch SAML data (may need admin scope): %s", exc)
        console.print(f"[yellow]Warning: could not fetch SAML data (admin scope may be required) — {exc}[/]")

    # ── Collect repos ───────────────────────────────────────────────
    logger.info("Fetching repositories …")
    try:
        raw_repos = gh.get_org_repos(org_slug)
        for r in raw_repos:
            repo = RepoInfo(
                name=r["name"],
                full_name=r["full_name"],
                private=r["private"],
                fork=r["fork"],
                archived=r["archived"],
                size_kb=r.get("size", 0),
                default_branch=r.get("default_branch", "main"),
            )
            report.repos.append(repo)
        report.total_repos = len(report.repos)
        logger.info("Found %d repositories", report.total_repos)
    except Exception as exc:
        logger.error("Failed to fetch repos: %s", exc)
        console.print(f"[yellow]Warning: failed to fetch repositories — {exc}[/]")

    # ── Outside collaborators ───────────────────────────────────────
    logger.info("Fetching outside collaborators …")
    try:
        collabs = gh.get_outside_collaborators(org_slug)
        report.outside_collaborators = len(collabs)
        logger.info("Found %d outside collaborators", report.outside_collaborators)
    except Exception as exc:
        logger.warning("Could not fetch outside collaborators: %s", exc)
        console.print(f"[yellow]Warning: could not fetch outside collaborators — {exc}[/]")

    # ── Evaluate risks ──────────────────────────────────────────────
    report.risks = [copy.copy(r) for r in STATIC_RISKS]
    _run_automated_checks(report, cfg)

    return report


def _run_automated_checks(report: AssessmentReport, cfg: dict) -> None:
    """Run automated checks and mark pass/fail on applicable risks."""

    for risk in report.risks:
        if not risk.automated_check:
            continue

        if risk.id == "SSO-002":
            # Check: do all members have SAML identities linked?
            unlinked = [m for m in report.members if not m.saml_identity]
            risk.check_passed = len(unlinked) == 0
            if unlinked:
                risk.description += (
                    f"\n\n⚠ {len(unlinked)} member(s) have NO SAML identity linked: "
                    + ", ".join(m.login for m in unlinked[:10])
                    + ("…" if len(unlinked) > 10 else "")
                )

        elif risk.id == "SSO-004":
            # Flag members whose login looks like a service account
            sa_patterns = ("svc-", "bot-", "ci-", "automation", "service")
            service_accounts = [
                m for m in report.members
                if any(m.login.lower().startswith(p) for p in sa_patterns)
            ]
            risk.check_passed = len(service_accounts) == 0
            if service_accounts:
                risk.description += (
                    f"\n\n⚠ Found {len(service_accounts)} potential service account(s): "
                    + ", ".join(m.login for m in service_accounts)
                )

        elif risk.id == "EMU-003":
            risk.check_passed = report.outside_collaborators == 0
            if report.outside_collaborators:
                risk.description += (
                    f"\n\n⚠ {report.outside_collaborators} outside collaborator(s) found. "
                    "They will lose access in an EMU org."
                )

        elif risk.id == "EMU-005":
            repos_with_actions = [r for r in report.repos if r.has_actions]
            risk.check_passed = len(repos_with_actions) == 0
            if repos_with_actions:
                risk.description += (
                    f"\n\n⚠ {len(repos_with_actions)} repo(s) use GitHub Actions and "
                    "may need secrets/environment reconfiguration."
                )

        elif risk.id == "EMU-006":
            risk.check_passed = True  # informational; deeper check needs packages API

        elif risk.id == "VAL-002":
            risk.check_passed = None  # can't auto-check OAuth grants easily
