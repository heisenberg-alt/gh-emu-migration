# GitHub Enterprise ADFS → Entra ID SSO + EMU Migration POC

A CLI tool that **assesses risks**, **generates step-by-step migration plans**, and **automates** the migration from **ADFS-based SAML SSO** to **Entra ID** for a GitHub Enterprise organization, including the transition to **Enterprise Managed Users (EMU)**.

---

## Quick Start

```bash
# 1. Install (creates .venv automatically)
cd gh-emu-migration
uv sync

# 2. Run the offline demo (no credentials needed)
uv run emu-migrate demo

# 3. For real usage: configure credentials
cp config.example.yaml config.yaml
# Edit config.yaml with your GitHub + Entra ID details

# 4. Run assessment against your org
uv run emu-migrate assess

# 5. View the full migration plan
uv run emu-migrate plan

# 6. Generate a Markdown report
uv run emu-migrate report

# 7. Generate GEI migration script
uv run emu-migrate generate-gei-script
```

---

## What This Tool Does

### 1. Risk Assessment (`emu-migrate assess`)

Connects to your GitHub Enterprise organization and:

- Inventories all **members** and their SAML identity linkages
- Inventories all **repositories** (size, Actions usage, archive status)
- Counts **outside collaborators** (not supported in EMU)
- Detects **service accounts** that may break during IdP switch
- Evaluates **13 risks** across four phases with severity ratings
- Runs **automated checks** where possible (unlinked SAML users, service accounts, outside collaborators, Actions usage)
- Outputs a JSON report for programmatic consumption

### 2. SSO Switch Plan (`emu-migrate plan --phase sso`)

Generates a 10-step plan to switch SAML SSO from ADFS to Entra ID:

1. Register Enterprise App in Entra ID
2. Configure SAML claim rules (with NameID matching guidance)
3. Assign user groups
4. Download Entra ID SAML metadata
5. Test with staging org
6. Announce maintenance window
7. Update GitHub org SAML settings
8. Validate with pilot users
9. Require SAML SSO
10. Decommission ADFS

### 3. EMU Migration Plan (`emu-migrate plan --phase emu`)

Generates a 14-step plan to migrate to Enterprise Managed Users:

1. Verify EMU entitlement
2. Create EMU enterprise
3. Configure Entra ID SAML for EMU
4. Configure SCIM provisioning
5. Assign user groups for SCIM
6. Validate provisioned accounts
7. Create target org in EMU enterprise
8. Install GitHub Enterprise Importer (GEI)
9. Dry-run repo migration
10. Full repo migration
11. Reclaim mannequins (identity mapping)
12. Validate developer workflow
13. Re-create integrations
14. Decommission old org

### 4. GEI Script Generation (`emu-migrate generate-gei-script`)

Auto-generates a bash script with one `gh gei migrate-repo` command per non-archived repository.

### 5. Full Report (`emu-migrate report`)

Combines everything into a single Markdown document saved to `reports/migration-report.md`.

---

## Configuration

Copy `config.example.yaml` to `config.yaml`. Key sections:

| Section | Purpose |
|---------|---------|
| `github` | Enterprise/org slug, PAT token |
| `adfs` | Current ADFS metadata (for NameID comparison) |
| `entra_id` | Entra ID tenant, app registration details |
| `emu` | Short code, group mappings |
| `migration` | Dry-run mode, output paths, notifications |

Secrets can also be set via environment variables:

```bash
export GH_TOKEN="ghp_..."
export ENTRA_TENANT_ID="..."
export ENTRA_CLIENT_SECRET="..."
```

---

## Key Risks Identified

| ID | Severity | Risk |
|----|----------|------|
| SSO-001 | 🔴 CRITICAL | SSO downtime during IdP switch |
| SSO-002 | 🟠 HIGH | SAML NameID mismatch between ADFS and Entra ID |
| EMU-001 | 🔴 CRITICAL | Personal accounts cannot be converted to EMU in-place |
| EMU-002 | 🔴 CRITICAL | Contribution history tied to personal accounts |
| EMU-003 | 🟠 HIGH | Outside collaborators not supported in EMU |
| EMU-004 | 🟠 HIGH | Personal forks, stars, gists are lost |
| EMU-005 | 🟠 HIGH | Actions secrets need reconfiguration |
| VAL-001 | 🟠 HIGH | PATs and SSH keys need SSO re-authorization |

See the full risk catalogue (13 items) by running `emu-migrate assess` or `emu-migrate demo`.

---

## Architecture

```
src/emu_migration/
├── __init__.py
├── cli.py              # Click CLI entry point
├── config.py           # YAML config loader with env var overrides
├── models.py           # Data models (Risk, OrgMember, RepoInfo, etc.)
├── github_client.py    # GitHub REST + GraphQL API client
├── assessment.py       # Risk assessment engine with automated checks
├── sso_migration.py    # ADFS → Entra ID SSO switch planner
├── emu_migration.py    # EMU migration planner + GEI script generator
├── report.py           # Markdown + Rich console report output
└── demo.py             # Offline demo with synthetic data
```

---

## Prerequisites

- Python 3.10+
- GitHub Enterprise Cloud organization with admin access
- GitHub PAT with scopes: `admin:org`, `read:user`, `user:email`
- Entra ID (Azure AD) tenant with Global Admin or Application Admin role
- [GitHub CLI](https://cli.github.com/) with the [GEI extension](https://github.com/github/gh-gei) (for repo migration)

---

## Important Notes

1. **EMU is a one-way migration**: EMU accounts are fundamentally different from personal accounts. There is no rollback to personal accounts once repos are migrated.

2. **Run in dry-run mode first**: The tool defaults to `dry_run: true` in config. Review all plans and reports before changing to live mode.

3. **Outside collaborators**: EMU does not support outside collaborators. They must be handled before migration (convert to guests via Entra B2B, or move shared repos to a non-EMU org).

4. **Contribution history**: Commits from personal accounts will appear as "mannequins" after migration. Use GEI's mannequin reclaim feature to remap them to EMU accounts.

5. **This is a POC**: This tool generates plans and reports. The actual SSO configuration changes and SCIM setup are manual steps performed in the Azure Portal and GitHub settings UI.
