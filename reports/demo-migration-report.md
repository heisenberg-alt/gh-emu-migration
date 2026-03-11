# GitHub Enterprise Migration Report
## ADFS → Entra ID SSO + EMU Migration

- **Enterprise**: contoso-enterprise
- **Organization**: contoso-dev
- **Generated**: 2026-03-11T13:12:48.006473+00:00
- **Members**: 6
- **Repositories**: 6
- **Outside Collaborators**: 2
- **SAML SSO Configured**: Yes

## Organization Members

| Login | Role | SAML Linked | Email |
|-------|------|-------------|-------|
| jdoe | admin | ✅ | jdoe@contoso.com |
| bsmith | member | ✅ | bsmith@contoso.com |
| agarcia | member | ✅ | agarcia@contoso.com |
| tchen | member | ❌ | tchen@contoso.com |
| svc-ci-bot | member | ✅ | ci@contoso.com |
| mjohnson | member | ✅ | mjohnson@contoso.com |

## Risk Assessment

### Sso Switch

#### 🔴 [SSO-001] SSO downtime during IdP switch  ⬜
**Severity**: CRITICAL

Changing the SAML IdP from ADFS to Entra ID requires updating the SSO configuration on the GitHub Enterprise organization settings page. During this window members cannot authenticate via SSO.

**Mitigation**: Schedule the cut-over during a maintenance window. Pre-configure the Entra ID Enterprise App and test with a staging org first. Keep ADFS running as fallback until validation completes.

#### 🟠 [SSO-002] SAML NameID mismatch between ADFS and Entra ID  ❌
**Severity**: HIGH

ADFS may use a different NameID format (e.g. Windows domain\user) than Entra ID (typically UPN or email). A mismatch breaks existing SAML identity linkages; users must re-authenticate and re-link.

⚠ 1 member(s) have NO SAML identity linked: tchen

**Mitigation**: Audit current ADFS NameID claim rules. Configure the Entra ID Enterprise App to emit the exact same NameID format and value. If that's not possible, plan for a re-link step for all users.

#### 🟡 [SSO-003] Conditional Access policies may block GitHub SSO  ⬜
**Severity**: MEDIUM

Entra ID Conditional Access policies (MFA, device compliance, IP restrictions) could prevent users from completing SAML sign-in to GitHub if not properly scoped.

**Mitigation**: Review Conditional Access policies applied to the GitHub Enterprise App in Entra ID. Create exceptions or targeted policies as needed.

#### 🟡 [SSO-004] Service accounts relying on ADFS tokens  ❌
**Severity**: MEDIUM

CI/CD pipelines or automation that authenticates through ADFS-based SAML may break when the IdP changes.

⚠ Found 1 potential service account(s): svc-ci-bot

**Mitigation**: Inventory all service accounts and PATs. Service accounts should use GitHub Apps or fine-grained PATs that don't require SSO. Authorize them after the new SSO config is active.

### Emu Migration

#### 🔴 [EMU-001] Personal accounts cannot be converted to EMU in-place  ⬜
**Severity**: CRITICAL

GitHub EMU accounts are distinct from personal accounts. There is no automated path to convert a personal account into a managed one. Users must be provisioned as new EMU accounts (login_shortcode) and repo access must be re-granted.

**Mitigation**: Create a new EMU-enabled enterprise. Provision users via SCIM from Entra ID. Use GitHub's Enterprise migration tooling (GEI) to transfer repositories. Users will have new @_shortcode logins.

#### 🔴 [EMU-002] Contribution history is tied to personal accounts  ⬜
**Severity**: CRITICAL

Commits, issues, PRs, and reviews authored by personal accounts will show as authored by those personal accounts (now external to the org). EMU accounts are separate identities.

**Mitigation**: Use mannequin reclaim (Enterprise Importer) to map old identities to new EMU accounts after repo migration. Communicate to users that their profile contribution graphs will reset on the EMU account.

#### 🟠 [EMU-003] Outside collaborators are not supported in EMU  ❌
**Severity**: HIGH

EMU organizations do not allow outside collaborators. External contributors with access to private repos lose access.

⚠ 2 outside collaborator(s) found.

**Mitigation**: Audit outside collaborators. Move shared repos to a non-EMU org, use GitHub's repository forking, or convert collaborators to guest accounts if Entra B2B is available.

#### 🟠 [EMU-004] Personal forks, stars, and gists are lost  ⬜
**Severity**: HIGH

EMU accounts cannot fork to personal namespaces or retain stars/gists from the old personal account.

**Mitigation**: Notify users in advance. Provide a script for users to export their gists and starred repos list before migration.

#### 🟠 [EMU-005] GitHub Actions secrets and environments need reconfiguration  ❌
**Severity**: HIGH

Organization and repo-level Actions secrets, environments, and OIDC trust policies reference the old org/enterprise. After migration they must be recreated.

⚠ 4 repo(s) use GitHub Actions.

**Mitigation**: Export all secrets metadata (not values) before migration. Document each repo's Actions configuration. Re-create secrets in the new EMU org.

#### 🟡 [EMU-006] GitHub Packages may need re-publishing  ✅
**Severity**: MEDIUM

Packages published under the old org namespace won't transfer automatically if the org slug changes.

**Mitigation**: Keep the same org slug when possible. If the slug changes, re-publish critical packages under the new namespace and update downstream references.

#### 🟡 [EMU-007] SCIM provisioning errors may orphan accounts  ⬜
**Severity**: MEDIUM

If SCIM provisioning from Entra ID fails for some users, they won't have EMU accounts and can't access the new org.

**Mitigation**: Test SCIM provisioning thoroughly with a small pilot group. Monitor the Entra ID provisioning logs. Have a rollback plan.

### Validation

#### 🟠 [VAL-001] PATs and SSH keys need SSO authorization  ⬜
**Severity**: HIGH

After enabling SSO with a new IdP, all PATs and SSH keys must be re-authorized for SSO. Until then, API/git operations fail.

**Mitigation**: Communicate to all users before migration. Provide step-by-step instructions for authorizing tokens/keys for the new SSO config.

#### 🟡 [VAL-002] GitHub Apps and OAuth Apps need re-approval  ⬜
**Severity**: MEDIUM

Third-party and internal GitHub/OAuth Apps may need to be re-approved under the org's new SSO policy.

**Mitigation**: List all installed GitHub Apps and OAuth App grants before migration. Re-approve them in the new org after migration.

## Phase 1: SAML SSO Switch (ADFS → Entra ID)

### Step 1: Register Enterprise Application in Entra ID  `[MANUAL]`

In Azure Portal → Entra ID → Enterprise Applications, create or locate the app 'GitHub Enterprise Managed User'. Use the GitHub SAML template from the gallery.

  Tenant ID : a1b2c3d4-e5f6-7890-abcd-ef1234567890
  Identifier: https://github.com/orgs/contoso-dev
  Reply URL : https://github.com/orgs/contoso-dev/saml/consume

### Step 2: Configure SAML claim rules in Entra ID  `[MANUAL]`

Set the following SAML claims on the Enterprise App:

  NameID            → user.userprincipalname (or match your ADFS format)
  http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress → user.mail
  http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name → user.userprincipalname

⚠ CRITICAL: The NameID value MUST match the value ADFS currently emits, or all existing SAML identity links will break and users must re-link.

### Step 3: Assign users and groups in Entra ID  `[MANUAL]`

Assign the appropriate Entra ID groups to the Enterprise App:

  Owners group  → GitHub-Org-Owners
  Members group → GitHub-Org-Members

All users who need GitHub access must be in one of these groups.

### Step 4: Download Entra ID SAML metadata  `[MANUAL]`

From the Enterprise App's Single sign-on page, download:
  • Federation Metadata XML
  • Certificate (Base64)
  • Login URL
  • Azure AD Identifier (Entity ID)

You'll need these for the GitHub side configuration.

### Step 5: (Optional) Test with staging organization  `[MANUAL]`

If you have a staging/test GitHub org, configure SSO there first with the Entra ID values to validate the end-to-end flow before touching production.

### Step 6: Announce maintenance window  `[MANUAL]`

Communicate to all org members:
  • Date/time of the SSO switch
  • Expected downtime (15–30 min for config change)
  • They will need to re-authenticate after the switch
  • PATs and SSH keys must be re-authorized for SSO

### Step 7: Update GitHub org SAML SSO settings  `[MANUAL]`

Go to github.com/organizations/contoso-dev/settings/security

  1. Under SAML single sign-on, click Edit
  2. Replace the Sign on URL with the Entra ID Login URL
  3. Replace the Issuer with the Entra ID Azure AD Identifier
  4. Replace the Public certificate with the Entra ID signing cert
  5. Click 'Test SAML configuration' and verify it succeeds
  6. Click Save

⚠ Do NOT enable 'Require SAML SSO' until validation is complete.

### Step 8: Validate SSO sign-in with pilot users  `[MANUAL]`

Have 3–5 pilot users sign out and sign back in via the new SSO flow.
Verify:
  • They can authenticate through Entra ID
  • Their SAML identity is correctly linked
  • They can access repos and perform git operations
  • MFA prompts work as expected

### Step 9: Require SAML SSO authentication  `[MANUAL]`

Once validated, go to github.com/organizations/contoso-dev/settings/security
and enable 'Require SAML SSO authentication for all members'.

Members who haven't linked their identity will receive an email prompting them to authenticate.

### Step 10: Decommission ADFS relying party trust  `[MANUAL]`

After confirming all users can authenticate via Entra ID:
  1. Monitor ADFS sign-in logs for 1–2 weeks for stragglers
  2. Remove the GitHub relying party trust from ADFS
  3. Update internal documentation

## Phase 2: EMU Migration

### Step 1: Verify EMU enterprise entitlement  `[MANUAL]`

Contact your GitHub account team to confirm that enterprise 'contoso-enterprise' is eligible for Enterprise Managed Users. EMU requires GitHub Enterprise Cloud with EMU enabled at the enterprise level — this is a separate enterprise from your current one.

### Step 2: Create new EMU-enabled enterprise (if needed)  `[MANUAL]`

GitHub will provision a new EMU enterprise. You'll get a setup user with the login 'contoso_admin'. Use this account to perform initial configuration.

⚠ The EMU enterprise is separate from your existing enterprise. Repos must be migrated over.

### Step 3: Configure Entra ID SAML SSO for EMU enterprise  `[MANUAL]`

Using the EMU setup user, configure SAML SSO:

  1. In Entra ID, create a new Enterprise App for EMU (tenant: a1b2c3d4-e5f6-7890-abcd-ef1234567890)
  2. Use the GitHub EMU SAML template from the Entra gallery
  3. Set Identifier (Entity ID): https://github.com/enterprises/contoso-enterprise
  4. Set Reply URL: https://github.com/enterprises/contoso-enterprise/saml/consume
  5. Configure NameID = user.userprincipalname
  6. On the GitHub enterprise settings page, enter the SAML config

### Step 4: Configure SCIM provisioning in Entra ID  `[MANUAL]`

Enable automatic provisioning on the Entra ID Enterprise App:

  1. Go to Provisioning → Get started
  2. Set Provisioning Mode = Automatic
  3. Tenant URL: https://api.github.com/scim/v2/enterprises/contoso-enterprise
  4. Secret Token: generate a PAT from the contoso_admin user with admin:enterprise scope
  5. Test Connection
  6. Under Mappings, verify user attribute mappings:
     • userName → formatted as handle_shortcode
     • emails[type eq "work"].value → user.mail
     • name.givenName → user.givenname
     • name.familyName → user.surname

### Step 5: Assign user groups for SCIM provisioning  `[MANUAL]`

Assign the Entra ID groups to the EMU Enterprise App:

  Owners group  → GitHub-Org-Owners
  Members group → GitHub-Org-Members

Start provisioning. Entra ID will create EMU accounts with the 'contoso' suffix (e.g., jdoe_contoso).

### Step 6: Validate SCIM-provisioned accounts  `[MANUAL]`

Verify that EMU accounts appear in the enterprise:

  1. Go to github.com/enterprises/contoso-enterprise/people
  2. Confirm all expected users are listed
  3. Check that logins follow the pattern user_contoso
  4. Have pilot users sign in via SSO and verify access

### Step 7: Create target organization in EMU enterprise  `[MANUAL]`

Create an organization (e.g., 'contoso-dev' or 'contoso-dev-emu') within the EMU enterprise. Configure:
  • Base permissions
  • Team sync from Entra ID groups
  • Repository creation permissions

### Step 8: Install and configure GitHub Enterprise Importer (GEI)  `[AUTOMATED]`

Install the GEI CLI:
  gh extension install github/gh-gei

Generate migration script:
  gh gei generate-script \
    --github-source-org contoso-dev \
    --github-target-org contoso-dev-emu \
    --output migrate.sh

Review the generated script. It will contain one gh gei migrate-repo command per repository.

### Step 9: Run repository migration (dry-run)  `[AUTOMATED]`

Execute the migration in dry-run mode first:

  export GH_SOURCE_PAT=<source org admin PAT>
  export GH_TARGET_PAT=<EMU enterprise admin PAT>

  gh gei migrate-repo \
    --github-source-org contoso-dev \
    --source-repo <repo-name> \
    --github-target-org contoso-dev-emu \
    --target-repo <repo-name>

Start with a few non-critical repos. Verify:
  • All branches transferred
  • All PRs/issues transferred
  • Branch protections transferred
  • Actions workflows present (secrets need manual setup)

### Step 10: Run full repository migration  `[AUTOMATED]`

After validating the pilot repos, run the full migration script.
Monitor the migration log for errors.

Post-migration per-repo checklist:
  □ Verify default branch
  □ Re-create branch protection rules if needed
  □ Re-create Actions secrets and environments
  □ Update any hardcoded org references in workflows
  □ Re-configure webhooks

### Step 11: Reclaim mannequins (map old identities to EMU accounts)  `[AUTOMATED]`

After migration, commits/PRs from old personal accounts show as 'mannequins'. Reclaim them:

  gh gei generate-mannequin-csv \
    --github-target-org contoso-dev-emu \
    --output mannequins.csv

Edit mannequins.csv to map old logins to new EMU logins:
  old-login → new-login_contoso

  gh gei reclaim-mannequin \
    --github-target-org contoso-dev-emu \
    --csv mannequins.csv

### Step 12: Validate end-to-end developer workflow  `[MANUAL]`

Have pilot users verify the full workflow in the new EMU org:

  1. Sign in via Entra ID SSO
  2. Clone a repo over HTTPS (authorize PAT for SSO)
  3. Push a commit
  4. Open a pull request
  5. Trigger a CI workflow via GitHub Actions
  6. Verify team memberships and repo access
  7. Verify that old commit history shows correct attribution

### Step 13: Re-create GitHub Apps and integrations  `[MANUAL]`

Reinstall or re-approve all GitHub Apps and integrations:
  • CI/CD integrations (Azure DevOps, Jenkins, etc.)
  • Security scanners (Dependabot, CodeQL, Snyk, etc.)
  • Project management tools (Jira, Linear, etc.)
  • Notification services (Slack, Teams, etc.)

### Step 14: Update DNS/bookmarks and decommission old org  `[MANUAL]`

1. Add a README to the old org (contoso-dev) pointing to the new EMU org
2. Archive all repos in the old org
3. Update internal documentation and bookmarks
4. After a bake-in period (2–4 weeks), remove the old org
5. Update any go-links or redirects
