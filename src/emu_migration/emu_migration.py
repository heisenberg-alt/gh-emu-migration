"""EMU migration planner and executor."""

from __future__ import annotations

import logging
import shlex
from typing import Any

from .models import MigrationPhase, MigrationPlan, MigrationStep

logger = logging.getLogger(__name__)


def build_emu_migration_plan(cfg: dict[str, Any]) -> MigrationPlan:
    """Generate the ordered steps to migrate from personal accounts to EMU."""
    org = cfg["github"]["organization"]
    enterprise = cfg["github"]["enterprise"]
    short_code = cfg.get("emu", {}).get("short_code", "company")
    tenant = cfg["entra_id"]["tenant_id"]
    dry_run = cfg.get("migration", {}).get("dry_run", True)

    steps = [
        # ── Phase A: Preparation ────────────────────────────────────
        MigrationStep(
            order=1,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Verify EMU enterprise entitlement",
            description=(
                f"Contact your GitHub account team to confirm that enterprise "
                f"'{enterprise}' is eligible for Enterprise Managed Users. "
                "EMU requires GitHub Enterprise Cloud with EMU enabled at the "
                "enterprise level — this is a separate enterprise from your current one."
            ),
            manual=True,
        ),
        MigrationStep(
            order=2,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Create new EMU-enabled enterprise (if needed)",
            description=(
                "GitHub will provision a new EMU enterprise. You'll get a setup user "
                f"with the login '{short_code}_admin'. Use this account to perform "
                "initial configuration.\n\n"
                "⚠ The EMU enterprise is separate from your existing enterprise. "
                "Repos must be migrated over."
            ),
            manual=True,
        ),
        MigrationStep(
            order=3,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Configure Entra ID SAML SSO for EMU enterprise",
            description=(
                "Using the EMU setup user, configure SAML SSO:\n\n"
                f"  1. In Entra ID, create a new Enterprise App for EMU (tenant: {tenant})\n"
                "  2. Use the GitHub EMU SAML template from the Entra gallery\n"
                f"  3. Set Identifier (Entity ID): https://github.com/enterprises/{enterprise}\n"
                f"  4. Set Reply URL: https://github.com/enterprises/{enterprise}/saml/consume\n"
                "  5. Configure NameID = user.userprincipalname\n"
                "  6. On the GitHub enterprise settings page, enter the SAML config"
            ),
            manual=True,
        ),
        MigrationStep(
            order=4,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Configure SCIM provisioning in Entra ID",
            description=(
                "Enable automatic provisioning on the Entra ID Enterprise App:\n\n"
                "  1. Go to Provisioning → Get started\n"
                "  2. Set Provisioning Mode = Automatic\n"
                f"  3. Tenant URL: https://api.github.com/scim/v2/enterprises/{enterprise}\n"
                f"  4. Secret Token: generate a PAT from the {short_code}_admin user "
                "with admin:enterprise scope\n"
                "  5. Test Connection\n"
                "  6. Under Mappings, verify user attribute mappings:\n"
                "     • userName → formatted as handle_shortcode\n"
                "     • emails[type eq \"work\"].value → user.mail\n"
                "     • name.givenName → user.givenname\n"
                "     • name.familyName → user.surname"
            ),
            manual=True,
        ),
        MigrationStep(
            order=5,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Assign user groups for SCIM provisioning",
            description=(
                "Assign the Entra ID groups to the EMU Enterprise App:\n\n"
                f"  Owners group  → {cfg.get('emu', {}).get('owners_group', 'TBD')}\n"
                f"  Members group → {cfg.get('emu', {}).get('members_group', 'TBD')}\n\n"
                "Start provisioning. Entra ID will create EMU accounts with the "
                f"'{short_code}' suffix (e.g., jdoe_{short_code})."
            ),
            manual=True,
        ),
        MigrationStep(
            order=6,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Validate SCIM-provisioned accounts",
            description=(
                "Verify that EMU accounts appear in the enterprise:\n\n"
                f"  1. Go to github.com/enterprises/{enterprise}/people\n"
                "  2. Confirm all expected users are listed\n"
                f"  3. Check that logins follow the pattern user_{short_code}\n"
                "  4. Have pilot users sign in via SSO and verify access"
            ),
            manual=True,
        ),

        # ── Phase B: Repository migration ───────────────────────────
        MigrationStep(
            order=7,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Create target organization in EMU enterprise",
            description=(
                f"Create an organization (e.g., '{org}' or '{org}-emu') within "
                f"the EMU enterprise. Configure:\n"
                "  • Base permissions\n"
                "  • Team sync from Entra ID groups\n"
                "  • Repository creation permissions"
            ),
            manual=True,
        ),
        MigrationStep(
            order=8,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Install and configure GitHub Enterprise Importer (GEI)",
            description=(
                "Install the GEI CLI:\n"
                "  gh extension install github/gh-gei\n\n"
                "Verify installation:\n"
                "  emu-migrate gei-check\n\n"
                "Set PATs for source and target orgs:\n"
                "  export GH_SOURCE_PAT=<source org admin PAT>\n"
                "  export GH_TARGET_PAT=<EMU enterprise admin PAT>"
            ),
            manual=False,
        ),
        MigrationStep(
            order=9,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Run repository migration (dry-run)",
            description=(
                "Execute a dry-run to validate repos before migrating:\n\n"
                f"  emu-migrate migrate --config config.yaml --dry-run\n\n"
                "Or migrate specific repos first:\n\n"
                f"  emu-migrate migrate --config config.yaml --dry-run "
                f"--repos test-backend-api --repos test-frontend-app\n\n"
                "Review the output. No data is transferred in dry-run mode."
            ),
            manual=False,
        ),
        MigrationStep(
            order=10,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Run full repository migration",
            description=(
                "After validating the dry-run, execute the live migration:\n\n"
                f"  emu-migrate migrate --config config.yaml --live\n\n"
                "This migrates all non-archived repos sequentially.\n"
                "Monitor the output and check reports/migration-log.json.\n\n"
                "Post-migration per-repo checklist:\n"
                "  □ Verify default branch\n"
                "  □ Re-create branch protection rules if needed\n"
                "  □ Re-create Actions secrets and environments\n"
                "  □ Update any hardcoded org references in workflows\n"
                "  □ Re-configure webhooks"
            ),
            manual=False,
        ),

        # ── Phase C: Identity reclaim ───────────────────────────────
        MigrationStep(
            order=11,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Reclaim mannequins (map old identities to EMU accounts)",
            description=(
                "After migration, commits/PRs from old personal accounts show as "
                "'mannequins'. Reclaim them:\n\n"
                "Generate the mapping CSV:\n"
                f"  emu-migrate reclaim-mannequins --config config.yaml --generate-only\n\n"
                "Review and edit reports/mannequin-mapping.csv, then reclaim:\n"
                f"  emu-migrate reclaim-mannequins --config config.yaml "
                f"--csv-file reports/mannequin-mapping.csv"
            ),
            manual=False,
        ),

        # ── Phase D: Validation ─────────────────────────────────────
        MigrationStep(
            order=12,
            phase=MigrationPhase.VALIDATION,
            title="Validate end-to-end developer workflow",
            description=(
                "Have pilot users verify the full workflow in the new EMU org:\n\n"
                "  1. Sign in via Entra ID SSO\n"
                "  2. Clone a repo over HTTPS (authorize PAT for SSO)\n"
                "  3. Push a commit\n"
                "  4. Open a pull request\n"
                "  5. Trigger a CI workflow via GitHub Actions\n"
                "  6. Verify team memberships and repo access\n"
                "  7. Verify that old commit history shows correct attribution"
            ),
            manual=True,
        ),
        MigrationStep(
            order=13,
            phase=MigrationPhase.VALIDATION,
            title="Re-create GitHub Apps and integrations",
            description=(
                "Reinstall or re-approve all GitHub Apps and integrations:\n"
                "  • CI/CD integrations (Azure DevOps, Jenkins, etc.)\n"
                "  • Security scanners (Dependabot, CodeQL, Snyk, etc.)\n"
                "  • Project management tools (Jira, Linear, etc.)\n"
                "  • Notification services (Slack, Teams, etc.)"
            ),
            manual=True,
        ),
        MigrationStep(
            order=14,
            phase=MigrationPhase.VALIDATION,
            title="Update DNS/bookmarks and decommission old org",
            description=(
                f"1. Add a README to the old org ({org}) pointing to the new EMU org\n"
                "2. Archive all repos in the old org\n"
                "3. Update internal documentation and bookmarks\n"
                "4. After a bake-in period (2–4 weeks), remove the old org\n"
                "5. Update any go-links or redirects"
            ),
            manual=True,
        ),
    ]

    return MigrationPlan(steps=steps, dry_run=dry_run)


def generate_mannequin_mapping(
    members: list[dict],
    short_code: str,
) -> list[dict[str, str]]:
    """Generate a proposed mapping from old personal logins to EMU logins.

    Returns a list of {"source": "old-login", "target": "old-login_shortcode"}.
    """
    return [
        {"source": m.get("login", ""), "target": f"{m.get('login', '')}_{short_code}"}
        for m in members
        if m.get("login")
    ]


def generate_gei_script(
    repos: list[str],
    source_org: str,
    target_org: str,
) -> str:
    """Generate a shell script for bulk repo migration using GEI."""
    lines = [
        "#!/usr/bin/env bash",
        "# Auto-generated GEI migration script",
        "# Review before running!",
        "set -euo pipefail",
        "",
        '# Export PATs before running:',
        '#   export GH_SOURCE_PAT="ghp_..."',
        '#   export GH_TARGET_PAT="ghp_..."',
        "",
    ]
    for repo in repos:
        lines.append(
            f'gh gei migrate-repo \\\n'
            f'  --github-source-org {shlex.quote(source_org)} \\\n'
            f'  --source-repo {shlex.quote(repo)} \\\n'
            f'  --github-target-org {shlex.quote(target_org)} \\\n'
            f'  --target-repo {shlex.quote(repo)} \\\n'
            f'  --wait\n'
        )
    lines.append('echo "Migration complete. Check logs for errors."')
    return "\n".join(lines)
