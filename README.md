# gh-emu-migration

CLI tool for migrating a GitHub Enterprise organization from ADFS SAML SSO to Entra ID, including the transition to Enterprise Managed Users (EMU). Assesses risks, generates migration plans, and produces GEI migration scripts.

## Quick Start

```bash
uv sync
uv run emu-migrate demo          # offline demo, no credentials needed
```

For a real org:

```bash
cp config.example.yaml config.yaml   # fill in GitHub + Entra ID details
uv run emu-migrate assess            # risk assessment against your org
uv run emu-migrate plan              # full migration plan
uv run emu-migrate report            # Markdown report
uv run emu-migrate generate-gei-script  # GEI repo migration script
```

## Prerequisites

| Requirement | Details |
|---|---|
| Python | 3.10+ |
| uv | Package manager — `irm https://astral.sh/uv/install.ps1 \| iex` (Windows) |
| GitHub PAT | Classic token with `admin:org`, `repo`, `read:user`, `user:email` scopes |
| GitHub Enterprise Cloud | Required for SAML/SSO and EMU features (free tier works for assessment only) |
| Entra ID tenant | Global Admin or Application Admin role |
| GitHub CLI + GEI | `gh extension install github/gh-gei` — for repo migration execution |

## Configuration

Copy `config.example.yaml` → `config.yaml`:

```yaml
github:
  enterprise: "your-enterprise"
  organization: "your-org"
  token: "ghp_..."

adfs:
  federation_metadata_url: "https://adfs.example.com/.../FederationMetadata.xml"

entra_id:
  tenant_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  client_id: "your-app-client-id"
  client_secret: ""

emu:
  target_enterprise: "your-org-emu"
  target_organization: "your-org-emu-org"
  shortcode: "YOUREMU"

migration:
  dry_run: true
```

Secrets can be set via environment variables instead:

```bash
export GH_TOKEN="ghp_..."
export ENTRA_TENANT_ID="..."
export ENTRA_CLIENT_SECRET="..."
```

## Commands

| Command | Description |
|---|---|
| `emu-migrate demo` | Run offline with synthetic data |
| `emu-migrate assess` | Connect to GitHub org, inventory members/repos, evaluate 13 risks |
| `emu-migrate plan --phase sso` | 10-step ADFS → Entra ID SSO switch plan |
| `emu-migrate plan --phase emu` | 14-step EMU migration plan |
| `emu-migrate plan` | Both plans |
| `emu-migrate report` | Full Markdown report to `reports/migration-report.md` |
| `emu-migrate generate-gei-script` | Bash script with `gh gei migrate-repo` per repo |
| `emu-migrate gei-check` | Verify `gh` CLI and `gh-gei` extension are installed |
| `emu-migrate migrate --dry-run` | Dry-run: lists repos that would be migrated |
| `emu-migrate migrate --live` | Execute live GEI migration (source → EMU org) |
| `emu-migrate reclaim-mannequins` | Generate mannequin mapping CSV and/or reclaim identities |
| `emu-migrate setup-test-org` | Provision a test org with sample repos and members |
| `emu-migrate live-test` | Automated end-to-end test suite (7 checks) |
| `emu-migrate check-entra` | Verify Entra ID / Azure CLI readiness |
| `emu-migrate setup-entra` | Create app registration, service principal, security groups |

All commands that hit the GitHub API accept `--config config.yaml`.

## What the Assessment Covers

- Member inventory with SAML identity linkage status
- Repository inventory (visibility, Actions usage, archive status)
- Outside collaborator detection (not supported in EMU)
- Service account identification
- 13 risks across 4 phases (assessment, SSO switch, EMU migration, validation)
- Automated checks where possible (unlinked SAML users, Actions workflows, outside collaborators)

## Risk Catalogue

| ID | Severity | Risk |
|---|---|---|
| SSO-001 | CRITICAL | SSO downtime during IdP switch |
| SSO-002 | HIGH | SAML NameID mismatch between ADFS and Entra ID |
| SSO-003 | MEDIUM | Conditional Access policy conflicts |
| SSO-004 | HIGH | Service account authentication breakage |
| EMU-001 | CRITICAL | Personal accounts cannot convert to EMU in-place |
| EMU-002 | CRITICAL | Contribution history tied to personal accounts |
| EMU-003 | HIGH | Outside collaborators not supported in EMU |
| EMU-004 | HIGH | Personal forks, stars, and gists are lost |
| EMU-005 | HIGH | Actions secrets and environments need reconfiguration |
| EMU-006 | MEDIUM | GitHub Packages registry migration |
| EMU-007 | MEDIUM | GitHub Apps and OAuth Apps need reconfiguration |
| VAL-001 | HIGH | PATs and SSH keys require SSO re-authorization |
| VAL-002 | MEDIUM | CI/CD pipeline authentication updates |

## Migration Phases

### Phase 1 — SSO Switch (ADFS → Entra ID)

10 steps: Register Entra ID Enterprise App → configure SAML claims → assign groups → download metadata → staging test → maintenance window → update GitHub SSO config → pilot validation → require SSO → decommission ADFS.

### Phase 2 — EMU Migration

14 steps: Verify EMU entitlement → create EMU enterprise → configure SAML + SCIM → provision accounts → create target org → install GEI → dry-run migration → full migration → reclaim mannequins → validate workflows → re-create integrations → decommission old org.

## Project Structure

```
src/emu_migration/
├── cli.py              # Click CLI (entry point: emu-migrate)
├── config.py           # YAML config loader, env var overrides
├── models.py           # Risk, OrgMember, RepoInfo, MigrationPlan
├── github_client.py    # REST + GraphQL API client
├── assessment.py       # Risk engine (13 risks, automated checks)
├── sso_migration.py    # SSO switch planner (10 steps)
├── emu_migration.py    # EMU planner (14 steps) + GEI script generator
├── report.py           # Markdown + Rich console output
└── demo.py             # Offline demo with synthetic Contoso data

tests/
├── setup_test_org.py   # GitHub org provisioner (5 repos, members, collaborators)
├── setup_entra_id.py   # Entra ID setup via Azure CLI
└── live_test.py        # E2E live test runner (7 checks)
```

## Important Constraints

- **EMU is one-way.** There is no rollback to personal accounts once repos are migrated to an EMU enterprise.
- **Outside collaborators must be handled first.** EMU does not support them. Options: Entra B2B guest accounts, or keep shared repos in a non-EMU org.
- **Contribution history appears as mannequins.** Commits from personal accounts are attributed to placeholder identities after migration. Use GEI mannequin reclaim to remap them.
- **Dry-run by default.** The tool defaults to `dry_run: true`. Review all output before switching to live mode.
- **This is a POC.** It generates plans, reports, and scripts. Actual SSO configuration and SCIM setup are performed in the Azure Portal and GitHub admin UI.

## Further Reading

- [LIVE_TESTING_GUIDE.md](LIVE_TESTING_GUIDE.md) — step-by-step guide for testing against a real org
- [TESTING.md](TESTING.md) — detailed test phases and troubleshooting
- [config.example.yaml](config.example.yaml) — annotated configuration template
