# Live Testing Guide: ADFS → Entra ID + EMU Migration

This guide walks you through testing the migration tool against a **real GitHub organization** end-to-end.

---

## Prerequisites

| Requirement | Purpose | How to get it |
|---|---|---|
| GitHub account (personal) | Org owner | You already have this |
| GitHub organization (free tier works) | Test target | github.com/organizations/new |
| GitHub PAT | API access | github.com/settings/tokens |
| 1-2 extra GitHub accounts | Test org members | Create or use friends' accounts |
| Azure subscription (optional) | Entra ID testing | portal.azure.com |
| Azure CLI (optional) | Entra ID automation | `winget install Microsoft.AzureCLI` |

---

## Phase 0: Create a Test Organization (5 min)

### Option A: Use an existing org
If you already have an org, skip to Phase 1. The tool is read-only during assessment.

### Option B: Create a new free org
1. Go to https://github.com/organizations/new
2. Pick **Free** plan
3. Choose a name like `mycompany-migration-test`
4. Skip the member invite step for now

---

## Phase 1: Provision the Test Environment (5 min)

### Step 1.1: Create a GitHub PAT

Go to https://github.com/settings/tokens?type=beta (Fine-grained) or https://github.com/settings/tokens/new (Classic).

**Classic PAT scopes needed:**
- `admin:org` — read org members, SAML identities, manage invitations
- `repo` — read repos, collaborators, Actions
- `workflow` — create Actions workflows in test repos
- `read:user` — read user profiles
- `user:email` — read user emails

### Step 1.2: Set up test repos and members

```powershell
cd c:\gh-emu-migration

# Option A: Via the CLI tool
emu-migrate setup-test-org \
  --org YOUR_ORG \
  --token ghp_YOUR_TOKEN \
  --invite friend1-github-username \
  --invite friend2-github-username \
  --collaborator some-external-user

# Option B: Via Python directly
python -m tests.setup_test_org \
  --org YOUR_ORG \
  --token ghp_YOUR_TOKEN \
  --invite friend1 friend2 \
  --collaborator external-user
```

This creates:
| Resource | Details |
|---|---|
| `test-backend-api` | Private repo with CI workflow |
| `test-frontend-app` | Private repo with CI workflow |
| `test-shared-libs` | Private repo with CI workflow |
| `test-public-docs` | Public repo (+ outside collaborator) |
| `test-archived-legacy` | Archived private repo |
| Member invitations | Sent to the `--invite` usernames |
| Outside collaborator | Added to `test-public-docs` |

> **Tip**: If you don't have extra GitHub accounts to invite, the assessment
> still works — it will just show 1 member (you) and 0 outside collaborators.

### Step 1.3: Accept invitations

If you invited other users, have them accept the org invitation at:
`https://github.com/orgs/YOUR_ORG/invitation`

---

## Phase 2: Configure the Tool (2 min)

### Step 2.1: Create config.yaml

```powershell
cd c:\gh-emu-migration
copy config.example.yaml config.yaml
```

### Step 2.2: Edit config.yaml

```yaml
github:
  enterprise: "your-enterprise"       # or just repeat the org name if no enterprise
  organization: "your-org-name"
  token: "ghp_your_actual_token"

adfs:
  federation_metadata_url: "https://adfs.yourcompany.com/FederationMetadata/2007-06/FederationMetadata.xml"
  entity_id: "https://adfs.yourcompany.com/adfs/services/trust"
  sso_url: "https://adfs.yourcompany.com/adfs/ls/"
  certificate_path: ""

entra_id:
  tenant_id: "your-azure-tenant-id"    # Get from Azure Portal → Entra ID → Overview
  client_id: "your-app-client-id"      # or a placeholder UUID for now
  client_secret: ""
  app_display_name: "GitHub Enterprise Managed User"

emu:
  short_code: "yourcompany"
  owners_group: "GitHub-Org-Owners"
  members_group: "GitHub-Org-Members"

migration:
  dry_run: true
  report_output: "reports/"
```

> **No Entra ID yet?** Use placeholder UUIDs like `11111111-2222-3333-4444-555555555555`.
> The GitHub assessment will still work — only the SSO readiness check will show warnings.

### Step 2.3: Or use environment variables

```powershell
$env:GH_TOKEN = "ghp_your_token"
$env:ENTRA_TENANT_ID = "your-tenant-id"
$env:ENTRA_CLIENT_SECRET = "your-secret"
```

---

## Phase 3: Run the Assessment (2 min)

### Step 3.1: Quick assessment

```powershell
emu-migrate assess
```

This connects to GitHub and produces:
- Member inventory (login, role, SAML link status)
- Repository inventory (name, size, Actions usage, archive status)
- Outside collaborator count
- Risk evaluation with automated checks

### Step 3.2: View migration plans

```powershell
# SSO switch plan only
emu-migrate plan --phase sso

# EMU migration plan only
emu-migrate plan --phase emu

# Both plans
emu-migrate plan
```

### Step 3.3: Generate the full report

```powershell
emu-migrate report
```

Output: `reports/migration-report.md` + `reports/assessment.json`

### Step 3.4: Generate GEI migration script

```powershell
emu-migrate generate-gei-script
```

Output: `reports/migrate-repos.sh` — a bash script with one `gh gei migrate-repo` per active repo.

---

## Phase 4: Run Automated Live Tests (2 min)

```powershell
# Standard test suite
emu-migrate live-test

# Full suite including GEI script generation
emu-migrate live-test --full
```

This runs 6–7 automated checks:
1. Config loading
2. Live assessment (members > 0, repos > 0, risks > 0)
3. SSO readiness check
4. SSO plan generation (10 steps)
5. EMU plan generation (14 steps)
6. Report generation (validates file output)
7. GEI script generation (--full only)

---

## Phase 5: Entra ID Setup (Optional, 15 min)

> ⚠️ Requires an Azure subscription with Entra ID (formerly Azure AD).
> Skip this if you just want to test the GitHub assessment side.

### Step 5.1: Log in to Azure

```powershell
az login
```

### Step 5.2: Check Entra readiness

```powershell
emu-migrate check-entra --tenant-id YOUR_TENANT_ID --org YOUR_ORG
```

This checks:
- Azure CLI authentication
- Ability to query Entra ID
- Existing GitHub-related Enterprise Apps
- Security groups for owner/member mapping

### Step 5.3: Create Entra ID resources

```powershell
emu-migrate setup-entra \
  --tenant-id YOUR_TENANT_ID \
  --org YOUR_ORG \
  --enterprise YOUR_ENTERPRISE
```

This creates:
- **App Registration**: "GitHub EMU - YOUR_ORG"
- **Service Principal**: Enterprise App entry
- **Security Groups**: GitHub-Org-Owners, GitHub-Org-Members

Then prints the remaining **manual steps** for SAML configuration.

### Step 5.4: Manual SAML configuration (Azure Portal)

1. Go to **Azure Portal → Entra ID → Enterprise Applications**
2. Find your app "GitHub EMU - YOUR_ORG"
3. **Single sign-on → SAML**:
   - Identifier (Entity ID): `https://github.com/orgs/YOUR_ORG`
   - Reply URL: `https://github.com/orgs/YOUR_ORG/saml/consume`
4. **Claims**:
   - NameID = `user.userprincipalname`
5. **Download**: Certificate (Base64) and Login URL
6. **Assign groups**: Add GitHub-Org-Owners and GitHub-Org-Members

### Step 5.5: Configure GitHub SAML SSO

> ⚠️ Requires **GitHub Enterprise Cloud** (paid plan) for SAML SSO.
> Free orgs cannot configure SAML.

1. Go to `github.com/organizations/YOUR_ORG/settings/security`
2. Enable SAML single sign-on
3. Enter the Entra ID Login URL, Azure AD Identifier, and certificate
4. Click **Test SAML configuration**
5. If test passes, click **Save**
6. (After validation) Enable **Require SAML SSO**

---

## Phase 6: Test the Full Migration Flow (for Enterprise Cloud)

> This phase requires GitHub Enterprise Cloud with EMU entitlement.
> Most organizations will work with GitHub's account team for this.

### Step 6.1: Verify the assessment catches real issues

```powershell
emu-migrate assess -v   # verbose mode
```

Look for:
- ❌ Members without SAML identity linked → SSO-002 risk
- ❌ Service accounts detected → SSO-004 risk
- ❌ Outside collaborators found → EMU-003 risk
- ❌ Repos with Actions → EMU-005 risk

### Step 6.2: Review the GEI script

```powershell
cat reports/migrate-repos.sh
```

### Step 6.3: Execute migration (with GitHub Enterprise Importer)

```powershell
# Install GEI
gh extension install github/gh-gei

# Dry-run one repo
$env:GH_SOURCE_PAT = "ghp_source_org_admin_token"
$env:GH_TARGET_PAT = "ghp_emu_enterprise_admin_token"

gh gei migrate-repo `
  --github-source-org YOUR_ORG `
  --source-repo test-backend-api `
  --github-target-org YOUR_ORG-emu `
  --target-repo test-backend-api
```

---

## Cleanup

```powershell
# Remove test repos from the org
emu-migrate setup-test-org --org YOUR_ORG --token ghp_TOKEN --cleanup

# Remove generated reports
Remove-Item -Recurse reports/
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `403 Forbidden` on members | PAT missing `admin:org` scope | Regenerate PAT with correct scopes |
| `404 Not Found` on org | Org name wrong or PAT not authorized | Verify org slug, SSO-authorize the PAT |
| SAML identities empty | No SAML SSO configured (free org) | Expected for free orgs — SSO needs Enterprise Cloud |
| `az login` fails | Azure CLI not installed | `winget install Microsoft.AzureCLI` |
| Assessment shows 0 members | PAT user is not an org admin | Make yourself org owner first |
| Config validation error | Placeholder values still in config.yaml | Replace all `REPLACE_ME` and `00000000` values |

---

## What You're Testing

| Feature | Free Org | Enterprise Cloud | EMU Enterprise |
|---|---|---|---|
| Member inventory | ✅ | ✅ | ✅ |
| Repo inventory | ✅ | ✅ | ✅ |
| Outside collaborators | ✅ | ✅ | N/A (not supported) |
| SAML identity audit | ❌ | ✅ | ✅ |
| Risk assessment | ✅ | ✅ | ✅ |
| SSO migration plan | ✅ | ✅ | ✅ |
| EMU migration plan | ✅ | ✅ | ✅ |
| GEI script generation | ✅ | ✅ | ✅ |
| Actual SSO switch | ❌ | ✅ | ✅ |
| Actual SCIM provisioning | ❌ | ❌ | ✅ |
| Actual repo migration | ❌ | ✅ (GEI) | ✅ (GEI) |

> **Bottom line**: Even with a free org, you can test ~70% of the tool's functionality.
> The assessment, risk engine, plan generation, and report output all work with any GitHub org.
