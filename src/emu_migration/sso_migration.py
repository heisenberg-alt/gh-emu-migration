"""ADFS → Entra ID SAML SSO migration planner and executor."""

from __future__ import annotations

import logging
from typing import Any

from .models import MigrationPhase, MigrationPlan, MigrationStep

logger = logging.getLogger(__name__)


def build_sso_switch_plan(cfg: dict[str, Any]) -> MigrationPlan:
    """Generate the ordered steps to switch SAML SSO from ADFS to Entra ID."""
    org = cfg["github"]["organization"]
    tenant = cfg["entra_id"]["tenant_id"]
    app_name = cfg["entra_id"].get("app_display_name", "GitHub Enterprise Managed User")
    dry_run = cfg.get("migration", {}).get("dry_run", True)

    steps = [
        # ── Pre-flight ──────────────────────────────────────────────
        MigrationStep(
            order=1,
            phase=MigrationPhase.SSO_SWITCH,
            title="Register Enterprise Application in Entra ID",
            description=(
                f"In Azure Portal → Entra ID → Enterprise Applications, create or "
                f"locate the app '{app_name}'. Use the GitHub SAML template from the "
                f"gallery.\n\n"
                f"  Tenant ID : {tenant}\n"
                f"  Identifier: https://github.com/orgs/{org}\n"
                f"  Reply URL : https://github.com/orgs/{org}/saml/consume"
            ),
            manual=True,
        ),
        MigrationStep(
            order=2,
            phase=MigrationPhase.SSO_SWITCH,
            title="Configure SAML claim rules in Entra ID",
            description=(
                "Set the following SAML claims on the Enterprise App:\n\n"
                "  NameID            → user.userprincipalname (or match your ADFS format)\n"
                "  http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress → user.mail\n"
                "  http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name → user.userprincipalname\n\n"
                "⚠ CRITICAL: The NameID value MUST match the value ADFS currently emits, "
                "or all existing SAML identity links will break and users must re-link."
            ),
            manual=True,
        ),
        MigrationStep(
            order=3,
            phase=MigrationPhase.SSO_SWITCH,
            title="Assign users and groups in Entra ID",
            description=(
                "Assign the appropriate Entra ID groups to the Enterprise App:\n\n"
                f"  Owners group  → {cfg.get('emu', {}).get('owners_group', 'TBD')}\n"
                f"  Members group → {cfg.get('emu', {}).get('members_group', 'TBD')}\n\n"
                "All users who need GitHub access must be in one of these groups."
            ),
            manual=True,
        ),
        MigrationStep(
            order=4,
            phase=MigrationPhase.SSO_SWITCH,
            title="Download Entra ID SAML metadata",
            description=(
                "From the Enterprise App's Single sign-on page, download:\n"
                "  • Federation Metadata XML\n"
                "  • Certificate (Base64)\n"
                "  • Login URL\n"
                "  • Azure AD Identifier (Entity ID)\n\n"
                "You'll need these for the GitHub side configuration."
            ),
            manual=True,
        ),
        MigrationStep(
            order=5,
            phase=MigrationPhase.SSO_SWITCH,
            title="(Optional) Test with staging organization",
            description=(
                "If you have a staging/test GitHub org, configure SSO there first "
                "with the Entra ID values to validate the end-to-end flow before "
                "touching production."
            ),
            manual=True,
        ),
        # ── Cut-over ────────────────────────────────────────────────
        MigrationStep(
            order=6,
            phase=MigrationPhase.SSO_SWITCH,
            title="Announce maintenance window",
            description=(
                "Communicate to all org members:\n"
                "  • Date/time of the SSO switch\n"
                "  • Expected downtime (15–30 min for config change)\n"
                "  • They will need to re-authenticate after the switch\n"
                "  • PATs and SSH keys must be re-authorized for SSO"
            ),
            manual=True,
        ),
        MigrationStep(
            order=7,
            phase=MigrationPhase.SSO_SWITCH,
            title="Update GitHub org SAML SSO settings",
            description=(
                f"Go to github.com/organizations/{org}/settings/security\n\n"
                "  1. Under SAML single sign-on, click Edit\n"
                "  2. Replace the Sign on URL with the Entra ID Login URL\n"
                "  3. Replace the Issuer with the Entra ID Azure AD Identifier\n"
                "  4. Replace the Public certificate with the Entra ID signing cert\n"
                "  5. Click 'Test SAML configuration' and verify it succeeds\n"
                "  6. Click Save\n\n"
                "⚠ Do NOT enable 'Require SAML SSO' until validation is complete."
            ),
            manual=True,
        ),
        MigrationStep(
            order=8,
            phase=MigrationPhase.SSO_SWITCH,
            title="Validate SSO sign-in with pilot users",
            description=(
                "Have 3–5 pilot users sign out and sign back in via the new SSO flow.\n"
                "Verify:\n"
                "  • They can authenticate through Entra ID\n"
                "  • Their SAML identity is correctly linked\n"
                "  • They can access repos and perform git operations\n"
                "  • MFA prompts work as expected"
            ),
            manual=True,
        ),
        MigrationStep(
            order=9,
            phase=MigrationPhase.SSO_SWITCH,
            title="Require SAML SSO authentication",
            description=(
                f"Once validated, go to github.com/organizations/{org}/settings/security\n"
                "and enable 'Require SAML SSO authentication for all members'.\n\n"
                "Members who haven't linked their identity will receive an email "
                "prompting them to authenticate."
            ),
            manual=True,
        ),
        MigrationStep(
            order=10,
            phase=MigrationPhase.SSO_SWITCH,
            title="Decommission ADFS relying party trust",
            description=(
                "After confirming all users can authenticate via Entra ID:\n"
                "  1. Monitor ADFS sign-in logs for 1–2 weeks for stragglers\n"
                "  2. Remove the GitHub relying party trust from ADFS\n"
                "  3. Update internal documentation"
            ),
            manual=True,
        ),
    ]

    return MigrationPlan(steps=steps, dry_run=dry_run)


def validate_sso_readiness(cfg: dict[str, Any]) -> list[str]:
    """Return a list of warnings/blockers for SSO switch readiness."""
    issues: list[str] = []

    entra = cfg.get("entra_id", {})
    if not entra.get("tenant_id") or str(entra["tenant_id"]).startswith("0000"):
        issues.append("Entra ID tenant_id is not configured (still placeholder).")

    if not entra.get("client_id") or str(entra["client_id"]).startswith("0000"):
        issues.append("Entra ID client_id is not configured (still placeholder).")

    emu = cfg.get("emu", {})
    if not emu.get("owners_group"):
        issues.append("No Entra ID owners group is defined for GitHub Org Owners mapping.")

    if not emu.get("members_group"):
        issues.append("No Entra ID members group is defined for GitHub Org Members mapping.")

    adfs = cfg.get("adfs", {})
    if not adfs.get("entity_id"):
        issues.append("ADFS entity_id not configured — needed for NameID comparison.")

    return issues
