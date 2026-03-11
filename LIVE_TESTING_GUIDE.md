# Live Testing Guide

Step-by-step instructions for testing the EMU Migration POC against a real GitHub organization.

---

## Prerequisites

- Python 3.10+ with the `emu-migrate` CLI installed (`pip install -e .`)
- A GitHub account
- (Optional) An Azure subscription for Entra ID testing

---

## 1. Create a GitHub Organization

If you don't already have one, create a **free** organization:

1. Go to <https://github.com/organizations/plan>
2. Pick the **Free** tier (sufficient for assessment and inventory testing)
3. Name it something like `my-emu-test-org`

> **Note:** Enterprise Cloud is required for SAML/SSO and EMU features. The free tier is enough to test assessment, repo inventory, and migration planning.

---

## 2. Create a Personal Access Token (PAT)

1. Go to <https://github.com/settings/tokens>
2. Click **Generate new token (classic)**
3. Select these scopes:
   - `admin:org` — manage org members, teams, and settings
   - `repo` — full repo access
   - `read:user` — read user profile data
   - `user:email` — read user email addresses
4. If you have GitHub Enterprise Cloud, also add:
   - `admin:enterprise` — required for SAML identity queries
5. Copy the token (starts with `ghp_`)

---

## 3. Provision the Test Organization

Use the built-in provisioner to populate your org with test repos, Actions workflows, and collaborators:

```bash
emu-migrate setup-test-org --org YOUR_ORG --token ghp_XXXX
```

This creates:

| Repository              | Description                        |
|-------------------------|------------------------------------|
| `test-backend-api`      | Private repo with Actions workflow |
| `test-frontend-app`     | Private repo with Actions workflow |
| `test-shared-libs`      | Private repo with Actions workflow |
| `test-public-docs`      | Public repo                        |
| `test-archived-legacy`  | Archived repo                      |

It also invites any members/collaborators you specify (see `--help` for options).

To clean up later:

```bash
emu-migrate setup-test-org --org YOUR_ORG --token ghp_XXXX --cleanup
```

---

## 4. Create Your Config File

Copy the example config and fill in your details:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

```yaml
github:
  enterprise: "your-enterprise"   # use "none" if on free tier
  organization: "YOUR_ORG"
  token: "ghp_XXXX"               # or set GH_TOKEN env var instead

adfs:
  federation_metadata_url: "https://adfs.example.com/FederationMetadata/2007-06/FederationMetadata.xml"
  relying_party_id: "https://github.com/orgs/YOUR_ORG/saml/metadata"

entra_id:
  tenant_id: "your-tenant-id"     # or set ENTRA_TENANT_ID env var
  client_id: "your-client-id"
  client_secret: ""               # or set ENTRA_CLIENT_SECRET env var

emu:
  target_enterprise: "YOUR_ORG-emu"
  target_organization: "YOUR_ORG-emu-org"
  shortcode: "YOUREMU"

migration:
  include_archived: false
  parallel_repos: 5
  dry_run: true
```

> **Tip:** You can set sensitive values via environment variables instead of putting them in the file:
> ```bash
> export GH_TOKEN=ghp_XXXX
> export ENTRA_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
> export ENTRA_CLIENT_SECRET=your-secret
> ```

---

## 5. Run the Live Assessment

```bash
emu-migrate assess --config config.yaml
```

This connects to your GitHub org and:
- Inventories all members and their roles
- Lists all repositories (private, public, archived, forked)
- Checks for SAML-linked identities (Enterprise Cloud only)
- Identifies outside collaborators
- Detects Actions workflow usage
- Evaluates 13 migration risks with automated checks

The output is a rich console report showing risks by severity.

---

## 6. Generate Migration Plans

### SSO Switch Plan (ADFS → Entra ID)

```bash
emu-migrate plan --config config.yaml --phase sso
```

Outputs a 10-step migration plan for switching your SAML SSO provider.

### EMU Migration Plan

```bash
emu-migrate plan --config config.yaml --phase emu
```

Outputs a 14-step plan for migrating to Enterprise Managed Users.

### Both Plans

```bash
emu-migrate plan --config config.yaml --phase all
```

---

## 7. Generate Reports

### Markdown Report

```bash
emu-migrate report --config config.yaml
```

Saves a full report to `reports/migration-report.md`.

### GEI Migration Script

```bash
emu-migrate generate-gei-script --config config.yaml
```

Generates a shell script for GitHub Enterprise Importer (`gh gei`) to migrate all repos.

Add `--full` to include mannequin reclaim commands:

```bash
emu-migrate generate-gei-script --config config.yaml --full
```

---

## 8. Run the Full Live Test Suite

```bash
emu-migrate live-test --config config.yaml
```

This runs 7 automated checks:

| #  | Check                  | What it verifies                         |
|----|------------------------|------------------------------------------|
| 1  | Config loading         | `config.yaml` parses and validates       |
| 2  | Live assessment        | GitHub API connection and data retrieval  |
| 3  | SSO readiness          | ADFS/Entra config completeness           |
| 4  | SSO plan generation    | 10 migration steps generated             |
| 5  | EMU plan generation    | 14 migration steps generated             |
| 6  | Report generation      | Markdown report saved successfully       |
| 7  | GEI script generation  | Migration script generated               |

---

## 9. (Optional) Entra ID Setup

Requires an Azure subscription and the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) (`az`).

### Check readiness

```bash
emu-migrate check-entra --tenant-id YOUR_TENANT_ID
```

Verifies:
- Azure CLI is installed and logged in
- You have access to the specified tenant
- Microsoft Graph permissions are available
- Reports any existing GitHub-related app registrations

### Provision Entra ID resources

```bash
emu-migrate setup-entra --tenant-id YOUR_TENANT_ID --org YOUR_ORG
```

Creates:
- **App Registration** — `GitHub EMU - YOUR_ORG` with SAML sign-on
- **Service Principal** — for the app registration
- **Security Groups** — `GitHub-Org-Owners` and `GitHub-Org-Members`

After running, you still need to manually:
1. Configure SAML URLs in the Azure Portal (Enterprise Applications → your app → Single sign-on)
2. Set the Entity ID to `https://github.com/orgs/YOUR_ORG`
3. Set the Reply URL to `https://github.com/orgs/YOUR_ORG/saml/consume`
4. Assign users/groups to the application
5. Download the Federation Metadata XML

---

## Feature Matrix by GitHub Tier

| Feature                     | Free Org | Enterprise Cloud | EMU Enterprise |
|-----------------------------|----------|------------------|----------------|
| Repo inventory              | ✅        | ✅                | ✅              |
| Member listing              | ✅        | ✅                | ✅              |
| Outside collaborator check  | ✅        | ✅                | ✅              |
| Actions workflow detection  | ✅        | ✅                | ✅              |
| SAML identity check         | ❌        | ✅                | ✅              |
| SSO migration planning      | ✅*       | ✅                | ✅              |
| EMU migration planning      | ✅*       | ✅                | ✅              |
| GEI script generation       | ✅        | ✅                | ✅              |
| Entra ID setup              | ✅        | ✅                | ✅              |

*Plans are generated but cannot be executed without Enterprise Cloud.

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Invalid or expired PAT | Regenerate token with correct scopes |
| `403 Forbidden` on SAML query | Missing `admin:enterprise` scope or not Enterprise Cloud | Add scope or skip SAML checks |
| `404 Not Found` on org | Org name typo or PAT doesn't have access | Verify org name and token scopes |
| Unicode/emoji errors on Windows | Terminal encoding is cp1252 | Upgrade to Windows Terminal, or run: `$env:PYTHONIOENCODING = "utf-8"` |
| `az` command not found | Azure CLI not installed | Install from https://aka.ms/installazurecli |
| `AADSTS700016` during Entra setup | Wrong tenant ID | Verify with `az account show` |
| Empty member list | PAT missing `admin:org` scope | Regenerate with `admin:org` |

---

## Quick Reference

```bash
# Demo (no GitHub connection needed)
emu-migrate demo

# Provision test org
emu-migrate setup-test-org --org MY_ORG --token ghp_XXXX

# Full assessment
emu-migrate assess --config config.yaml

# Migration plans
emu-migrate plan --config config.yaml --phase all

# Generate report
emu-migrate report --config config.yaml

# Generate GEI script
emu-migrate generate-gei-script --config config.yaml --full

# Automated test suite
emu-migrate live-test --config config.yaml

# Entra ID checks
emu-migrate check-entra --tenant-id TENANT_ID
emu-migrate setup-entra --tenant-id TENANT_ID --org MY_ORG

# Clean up test org
emu-migrate setup-test-org --org MY_ORG --token ghp_XXXX --cleanup
```
