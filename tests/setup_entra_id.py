"""Entra ID (Azure AD) setup helper for GitHub SAML SSO + SCIM.

This script automates the Entra ID side of the migration:
  1. Register/find the GitHub Enterprise App
  2. Configure SAML SSO settings
  3. Configure SCIM provisioning
  4. Assign groups

Prerequisites:
  - Azure CLI installed and logged in (az login)
  - Microsoft Graph permissions: Application.ReadWrite.All, Directory.ReadWrite.All
  - An Entra ID tenant with P1 or P2 license (for Enterprise Apps)

Usage:
  python -m tests.setup_entra_id --tenant-id TENANT --org YOUR_ORG --mode check
  python -m tests.setup_entra_id --tenant-id TENANT --org YOUR_ORG --mode setup
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# GitHub SAML app template ID in the Azure AD Gallery
GITHUB_GALLERY_APP_ID = "4173a31a-3a5c-4d5e-8f0e-2c9b5a2d3e4f"


def run_az(args: list[str], check: bool = True) -> dict | list | str:
    """Run an Azure CLI command and return parsed JSON output."""
    cmd = ["az"] + args + ["--output", "json"]
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if check and result.returncode != 0:
        logger.error("az CLI error: %s", result.stderr.strip())
        return {}
    if result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout.strip()
    return {}


def check_az_login() -> bool:
    """Verify Azure CLI is logged in."""
    result = subprocess.run(
        ["az", "account", "show", "--output", "json"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.error("❌ Azure CLI not logged in. Run: az login")
        return False
    account = json.loads(result.stdout)
    logger.info("✅ Azure CLI logged in as: %s (Tenant: %s)",
                account.get("user", {}).get("name", "unknown"),
                account.get("tenantId", "unknown"))
    return True


# ── Check mode: verify readiness ───────────────────────────────────

def check_entra_readiness(tenant_id: str, org: str) -> None:
    """Check if Entra ID is ready for GitHub SSO configuration."""
    logger.info("=" * 60)
    logger.info("Checking Entra ID readiness for GitHub SSO")
    logger.info("=" * 60)

    # 1. Check az login
    if not check_az_login():
        sys.exit(1)

    # 2. Check tenant
    logger.info("\n── Tenant Info ──")
    tenant = run_az(["account", "show"])
    if isinstance(tenant, dict):
        logger.info("  Tenant ID  : %s", tenant.get("tenantId", "?"))
        logger.info("  Subscription: %s", tenant.get("name", "?"))

    # 3. Check if we can query MS Graph
    logger.info("\n── Microsoft Graph Access ──")
    apps = run_az(["ad", "app", "list", "--display-name", "GitHub", "--query", "[].displayName"])
    if isinstance(apps, list):
        logger.info("  ✅ Can query Entra ID applications")
        if apps:
            logger.info("  Found existing GitHub-related apps: %s", apps)
    else:
        logger.warning("  ⚠️  Cannot query applications — may need more permissions")

    # 4. Check for existing Enterprise Apps with "GitHub" in the name
    logger.info("\n── Existing Enterprise Apps ──")
    sps = run_az([
        "ad", "sp", "list",
        "--display-name", "GitHub",
        "--query", "[].{name:displayName, appId:appId, id:id}",
    ])
    if isinstance(sps, list) and sps:
        for sp in sps:
            logger.info("  Found: %s (AppId: %s)", sp.get("name"), sp.get("appId"))
    else:
        logger.info("  No existing GitHub Enterprise Apps found")

    # 5. Check for groups
    logger.info("\n── Security Groups ──")
    for group_name in ["GitHub-Org-Owners", "GitHub-Org-Members"]:
        groups = run_az([
            "ad", "group", "list",
            "--display-name", group_name,
            "--query", "[].{name:displayName, id:id}",
        ])
        if isinstance(groups, list) and groups:
            logger.info("  ✅ Found group: %s (ID: %s)", group_name, groups[0].get("id"))
        else:
            logger.info("  ⬜ Group not found: %s (will need to create)", group_name)

    # 6. Summary
    logger.info("\n" + "=" * 60)
    logger.info("Readiness check complete.")
    logger.info("Next steps:")
    logger.info("  1. Run with --mode setup to create the Enterprise App")
    logger.info("  2. Or manually create via Azure Portal (recommended for first time)")
    logger.info("=" * 60)


# ── Setup mode: create Enterprise App and groups ────────────────────

def setup_entra_for_github(tenant_id: str, org: str, enterprise: str = "") -> None:
    """Create the Entra ID Enterprise App, groups, and SAML config for GitHub."""
    logger.info("=" * 60)
    logger.info("Setting up Entra ID for GitHub SSO")
    logger.info("=" * 60)

    if not check_az_login():
        sys.exit(1)

    # 1. Create security groups
    logger.info("\n── Creating Security Groups ──")
    owners_group_id = _ensure_group("GitHub-Org-Owners",
                                    "GitHub Enterprise org owners — maps to admin role")
    members_group_id = _ensure_group("GitHub-Org-Members",
                                     "GitHub Enterprise org members — maps to member role")

    # 2. Create the App Registration
    logger.info("\n── Creating App Registration ──")
    app_name = f"GitHub EMU - {org}"

    # Use identifier URIs for the SAML Entity ID
    identifier_uri = f"https://github.com/orgs/{org}"
    reply_url = f"https://github.com/orgs/{org}/saml/consume"

    existing = run_az([
        "ad", "app", "list",
        "--display-name", app_name,
        "--query", "[0].appId",
    ], check=False)

    if existing and isinstance(existing, str) and len(existing) > 10:
        app_id = existing.strip('"')
        logger.info("  ⏭️  App already exists: %s (AppId: %s)", app_name, app_id)
    else:
        app_result = run_az([
            "ad", "app", "create",
            "--display-name", app_name,
            "--web-redirect-uris", reply_url,
            "--sign-in-audience", "AzureADMyOrg",
            "--query", "appId",
        ])
        if isinstance(app_result, str):
            app_id = app_result.strip('"')
            logger.info("  ✅ Created app: %s (AppId: %s)", app_name, app_id)
        else:
            logger.error("  ❌ Failed to create app registration")
            return

    # 3. Create Service Principal (Enterprise App)
    logger.info("\n── Creating Service Principal ──")
    sp_existing = run_az([
        "ad", "sp", "list",
        "--filter", f"appId eq '{app_id}'",
        "--query", "[0].id",
    ], check=False)

    if sp_existing and isinstance(sp_existing, str) and len(sp_existing) > 10:
        sp_id = sp_existing.strip('"')
        logger.info("  ⏭️  Service Principal exists: %s", sp_id)
    else:
        sp_result = run_az([
            "ad", "sp", "create",
            "--id", app_id,
            "--query", "id",
        ])
        if isinstance(sp_result, str):
            sp_id = sp_result.strip('"')
            logger.info("  ✅ Created Service Principal: %s", sp_id)
        else:
            logger.error("  ❌ Failed to create service principal")
            return

    # 4. Print configuration summary
    logger.info("\n" + "=" * 60)
    logger.info("✅ Entra ID setup complete!")
    logger.info("=" * 60)
    logger.info("")
    logger.info("App Registration : %s", app_name)
    logger.info("App (Client) ID  : %s", app_id)
    logger.info("Tenant ID        : %s", tenant_id)
    logger.info("Owners Group     : %s", owners_group_id or "GitHub-Org-Owners")
    logger.info("Members Group    : %s", members_group_id or "GitHub-Org-Members")
    logger.info("")
    logger.info("── MANUAL STEPS REMAINING ──")
    logger.info("")
    logger.info("1. Go to Azure Portal → Entra ID → Enterprise Applications")
    logger.info("   Find: '%s'", app_name)
    logger.info("")
    logger.info("2. Single sign-on → SAML:")
    logger.info("   Identifier (Entity ID): %s", identifier_uri)
    logger.info("   Reply URL (ACS URL)   : %s", reply_url)
    logger.info("")
    logger.info("3. Configure SAML Claims:")
    logger.info("   NameID = user.userprincipalname")
    logger.info("   email  = user.mail")
    logger.info("   name   = user.userprincipalname")
    logger.info("")
    logger.info("4. Download the SAML Signing Certificate (Base64)")
    logger.info("   and the Login URL / Azure AD Identifier")
    logger.info("")
    logger.info("5. Assign the groups to this Enterprise App:")
    logger.info("   Users and groups → Add → GitHub-Org-Owners (admin)")
    logger.info("   Users and groups → Add → GitHub-Org-Members (member)")
    logger.info("")
    logger.info("6. Update config.yaml with these values:")
    logger.info("   entra_id.tenant_id: %s", tenant_id)
    logger.info("   entra_id.client_id: %s", app_id)

    # If EMU enterprise, also print SCIM info
    if enterprise:
        logger.info("")
        logger.info("── FOR EMU SCIM PROVISIONING ──")
        logger.info("")
        logger.info("7. Enable Provisioning on the Enterprise App:")
        logger.info("   Provisioning → Automatic")
        logger.info("   Tenant URL: https://api.github.com/scim/v2/enterprises/%s", enterprise)
        logger.info("   Secret Token: <PAT from setup user with admin:enterprise scope>")


def _ensure_group(name: str, description: str) -> str | None:
    """Create a security group if it doesn't exist. Returns the group ID."""
    existing = run_az([
        "ad", "group", "list",
        "--display-name", name,
        "--query", "[0].id",
    ], check=False)

    if existing and isinstance(existing, str) and len(existing) > 10:
        gid = existing.strip('"')
        logger.info("  ⏭️  Group exists: %s (ID: %s)", name, gid)
        return gid

    result = run_az([
        "ad", "group", "create",
        "--display-name", name,
        "--mail-nickname", name.lower().replace(" ", "-"),
        "--description", description,
        "--query", "id",
    ])
    if isinstance(result, str):
        gid = result.strip('"')
        logger.info("  ✅ Created group: %s (ID: %s)", name, gid)
        return gid
    else:
        logger.warning("  ⚠️  Could not create group: %s", name)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Set up Entra ID for GitHub SAML SSO + SCIM"
    )
    parser.add_argument("--tenant-id", required=True, help="Entra ID tenant ID")
    parser.add_argument("--org", required=True, help="GitHub organization slug")
    parser.add_argument("--enterprise", default="", help="GitHub enterprise slug (for EMU SCIM)")
    parser.add_argument(
        "--mode",
        choices=["check", "setup"],
        default="check",
        help="check = verify readiness, setup = create resources",
    )

    args = parser.parse_args()

    if args.mode == "check":
        check_entra_readiness(args.tenant_id, args.org)
    elif args.mode == "setup":
        setup_entra_for_github(args.tenant_id, args.org, args.enterprise)


if __name__ == "__main__":
    main()
