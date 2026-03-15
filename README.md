# gh-emu-migration

> **Disclaimer — Proof of Concept**
> This project is provided as a **proof of concept (POC)** for informational and evaluation purposes only. It is not production-ready software. The authors make **no guarantees, warranties, or representations** — express or implied — regarding its accuracy, reliability, completeness, or fitness for any particular purpose. Use of this tool is entirely at your own risk. Always validate migration plans and test thoroughly in a non-production environment before applying any changes to your GitHub Enterprise organization.

CLI + desktop app for migrating a GitHub Enterprise organization from ADFS SAML SSO to Entra ID, including the transition to Enterprise Managed Users (EMU). Assesses risks, generates migration plans, produces GEI migration scripts, and can execute migrations directly.

## Quick Start

```bash
uv sync
```

**Desktop app** (recommended):

```bash
uv run emu-migrate-desktop       # launches native GUI window
```

**CLI**:

```bash
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

Tokens are read exclusively from environment variables (never passed as CLI arguments):

```bash
export GH_SOURCE_PAT="ghp_..."     # source org PAT
export GH_TARGET_PAT="ghp_..."     # target EMU org PAT
export ENTRA_TENANT_ID="..."
export ENTRA_CLIENT_SECRET="..."
```

## Desktop App

The desktop app provides a native GUI via [pywebview](https://pywebview.flowrl.com/) (WebKit on macOS, Edge WebView2 on Windows). It exposes the same functionality as the CLI across five tabs:

| Tab | Description |
|---|---|
| Assessment | Risk assessment with severity badges and automated checks |
| Migration Plans | SSO switch (10 steps) and EMU migration (14 steps) plans |
| Report | Full Markdown report with copy/download |
| GEI Script | Generated `gh gei migrate-repo` script with copy/download |
| Execute Migration | Run GEI migration directly from the app (detect `gh` + `gh-gei`, dry-run / live) |

Launch with:

```bash
uv run emu-migrate-desktop           # production mode
uv run emu-migrate-desktop --debug   # opens browser dev tools
```

### Standalone Build

Build a distributable `.app` (macOS) or `.exe` (Windows) with PyInstaller:

```bash
uv pip install "pyinstaller>=6.0"
./packaging/build.sh               # outputs to dist/
./packaging/build.sh --clean       # clean build
```

## CLI Commands

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

All commands that hit the GitHub API accept `--config config.yaml`. A maximum of 500 repos are processed per run — split larger orgs into batches.

## Security

- **No tokens on the command line.** PATs are read from environment variables only (`GH_SOURCE_PAT`, `GH_TARGET_PAT`), never accepted as CLI arguments.
- **Token redaction in logs.** Any subprocess output that contains a PAT value is redacted before logging.
- **Config validation.** The desktop API validates required config fields before making API calls.
- **GraphQL error handling.** Malformed or error responses from the GitHub GraphQL API raise immediately instead of returning partial data.
- **Pagination limits.** REST and GraphQL pagination stops after 1 000 pages to prevent runaway requests.
- **Shell-safe scripts.** Generated GEI migration scripts use `shlex.quote()` for all interpolated values.

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
├── cli.py              # Click CLI entry point (emu-migrate)
├── desktop.py          # pywebview desktop app launcher (emu-migrate-desktop)
├── desktop_api.py      # Python ↔ JS bridge exposed to the GUI
├── ui/                 # Frontend SPA (HTML/CSS/JS, GitHub Primer Dark theme)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── config.py           # YAML config loader, env var overrides
├── models.py           # Risk, OrgMember, RepoInfo, MigrationPlan dataclasses
├── github_client.py    # REST + GraphQL API client with pagination
├── assessment.py       # Risk engine (13 risks, automated checks)
├── sso_migration.py    # SSO switch planner (10 steps)
├── emu_migration.py    # EMU planner (14 steps) + GEI script generator
├── gei.py              # GEI CLI wrapper (migrate-repo, mannequin reclaim)
├── report.py           # Markdown + Rich console output
├── demo.py             # Offline demo with synthetic Contoso data
└── _console.py         # Shared Rich Console singleton

packaging/
├── emu_migration.spec  # PyInstaller spec for .app / .exe builds
└── build.sh            # One-command build script

tests/
├── test_core.py        # 22 pytest unit tests
├── setup_test_org.py   # GitHub org provisioner (5 repos, members, collaborators)
├── setup_entra_id.py   # Entra ID setup via Azure CLI
└── live_test.py        # E2E live test runner (7 checks)
```

## Development

```bash
uv sync --extra dev            # install dev dependencies
uv run ruff check src/ tests/  # lint
uv run pytest tests/ -v        # run tests (22 unit tests)
```

## Important Constraints

- **EMU is one-way.** There is no rollback to personal accounts once repos are migrated to an EMU enterprise.
- **Outside collaborators must be handled first.** EMU does not support them. Options: Entra B2B guest accounts, or keep shared repos in a non-EMU org.
- **Contribution history appears as mannequins.** Commits from personal accounts are attributed to placeholder identities after migration. Use GEI mannequin reclaim to remap them.
- **Dry-run by default.** The tool defaults to `dry_run: true`. Review all output before switching to live mode.
- **500-repo batch limit.** CLI commands process up to 500 repos per run to keep API usage and script size manageable.
- **This is a POC.** It generates plans, reports, and scripts. Actual SSO configuration and SCIM setup are performed in the Azure Portal and GitHub admin UI.

## Further Reading

- [LIVE_TESTING_GUIDE.md](LIVE_TESTING_GUIDE.md) — step-by-step guide for testing against a real org
- [TESTING.md](TESTING.md) — detailed test phases and troubleshooting
- [config.example.yaml](config.example.yaml) — annotated configuration template
