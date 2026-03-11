"""EMU migration planner and executor."""

from __future__ import annotations

import logging
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
                "Generate migration script:\n"
                f"  gh gei generate-script \\\n"
                f"    --github-source-org {org} \\\n"
                f"    --github-target-org {org}-emu \\\n"
                "    --output migrate.sh\n\n"
                "Review the generated script. It will contain one gh gei migrate-repo "
                "command per repository."
            ),
            manual=False,
        ),
        MigrationStep(
            order=9,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Run repository migration (dry-run)",
            description=(
                "Execute the migration in dry-run mode first:\n\n"
                f"  export GH_SOURCE_PAT=<source org admin PAT>\n"
                f"  export GH_TARGET_PAT=<EMU enterprise admin PAT>\n\n"
                f"  gh gei migrate-repo \\\n"
                f"    --github-source-org {org} \\\n"
                f"    --source-repo <repo-name> \\\n"
                f"    --github-target-org {org}-emu \\\n"
                f"    --target-repo <repo-name>\n\n"
                "Start with a few non-critical repos. Verify:\n"
                "  • All branches transferred\n"
                "  • All PRs/issues transferred\n"
                "  • Branch protections transferred\n"
                "  • Actions workflows present (secrets need manual setup)"
            ),
            manual=False,
        ),
        MigrationStep(
            order=10,
            phase=MigrationPhase.EMU_MIGRATION,
            title="Run full repository migration",
            description=(
                "After validating the pilot repos, run the full migration script.\n"
                "Monitor the migration log for errors.\n\n"
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
                f"  gh gei generate-mannequin-csv \\\n"
                f"    --github-target-org {org}-emu \\\n"
                "    --output mannequins.csv\n\n"
                "Edit mannequins.csv to map old logins to new EMU logins:\n"
                f"  old-login → new-login_{short_code}\n\n"
                f"  gh gei reclaim-mannequin \\\n"
                f"    --github-target-org {org}-emu \\\n"
                "    --csv mannequins.csv"
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
            f'  --github-source-org "{source_org}" \\\n'
            f'  --source-repo "{repo}" \\\n'
            f'  --github-target-org "{target_org}" \\\n'
            f'  --target-repo "{repo}" \\\n'
            f'  --wait\n'
        )
    lines.append('echo "Migration complete. Check logs for errors."')
    return "\n".join(lines)
