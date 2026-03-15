"""Provision a demo GitHub organization for live testing.

This script uses the GitHub API to:
  1. Create test repositories in your org
  2. Invite personal accounts as members
  3. Add outside collaborators
  4. Create GitHub Actions workflows (to test Actions detection)
  5. Verify the setup is ready for migration testing

Prerequisites:
  - A GitHub org you own (free tier works for assessment testing)
  - A PAT with admin:org, repo, workflow scopes
  - At least one other GitHub account to invite (or use a second account)

Usage:
  python -m tests.setup_test_org --org YOUR_ORG --token ghp_xxx
  python -m tests.setup_test_org --org YOUR_ORG --token ghp_xxx --cleanup
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Any

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

API = "https://api.github.com"


class GitHubSetup:
    """Helper to provision a test organization."""

    def __init__(self, token: str, org: str):
        self.org = org
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _post(self, path: str, json: dict | None = None) -> requests.Response:
        resp = self.session.post(f"{API}{path}", json=json, timeout=30)
        return resp

    def _put(self, path: str, json: dict | None = None) -> requests.Response:
        resp = self.session.put(f"{API}{path}", json=json, timeout=30)
        return resp

    def _delete(self, path: str) -> requests.Response:
        resp = self.session.delete(f"{API}{path}", timeout=30)
        return resp

    def _get(self, path: str) -> requests.Response:
        resp = self.session.get(f"{API}{path}", timeout=30)
        return resp

    # ── Org info ────────────────────────────────────────────────────
    def verify_org(self) -> bool:
        resp = self._get(f"/orgs/{self.org}")
        if resp.status_code == 200:
            data = resp.json()
            logger.info("✅ Organization '%s' found (ID: %s)", data["login"], data["id"])
            logger.info("   Plan: %s | Repos: %s | Members: public=%s",
                        data.get("plan", {}).get("name", "free"),
                        data.get("public_repos", 0) + data.get("total_private_repos", 0),
                        data.get("public_members_count", 0))
            return True
        else:
            logger.error("❌ Cannot access org '%s': %s", self.org, resp.status_code)
            return False

    # ── Repos ───────────────────────────────────────────────────────
    def create_test_repos(self) -> list[str]:
        """Create a set of test repos with varied configurations."""
        repos = [
            {
                "name": "test-backend-api",
                "description": "[EMU-TEST] Sample backend API for migration testing",
                "private": True,
                "auto_init": True,
            },
            {
                "name": "test-frontend-app",
                "description": "[EMU-TEST] Sample frontend app for migration testing",
                "private": True,
                "auto_init": True,
            },
            {
                "name": "test-shared-libs",
                "description": "[EMU-TEST] Shared libraries for migration testing",
                "private": True,
                "auto_init": True,
            },
            {
                "name": "test-public-docs",
                "description": "[EMU-TEST] Public docs repo for migration testing",
                "private": False,
                "auto_init": True,
            },
            {
                "name": "test-archived-legacy",
                "description": "[EMU-TEST] Archived legacy repo for migration testing",
                "private": True,
                "auto_init": True,
            },
        ]

        created = []
        for repo in repos:
            resp = self._post(f"/orgs/{self.org}/repos", json=repo)
            if resp.status_code == 201:
                logger.info("✅ Created repo: %s/%s", self.org, repo["name"])
                created.append(repo["name"])
            elif resp.status_code == 422:
                logger.info("⏭️  Repo already exists: %s/%s", self.org, repo["name"])
                created.append(repo["name"])
            else:
                logger.error("❌ Failed to create %s: %s %s",
                             repo["name"], resp.status_code, resp.text[:200])

        # Archive the legacy repo
        self.session.patch(
            f"{API}/repos/{self.org}/test-archived-legacy",
            json={"archived": True},
            timeout=30,
        )
        logger.info("📦 Archived test-archived-legacy")

        return created

    def add_actions_workflow(self, repo: str) -> None:
        """Add a simple GitHub Actions workflow to a repo."""
        workflow_content = """name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: echo "Running tests..."
"""
        import base64
        encoded = base64.b64encode(workflow_content.encode()).decode()

        resp = self._put(
            f"/repos/{self.org}/{repo}/contents/.github/workflows/ci.yml",
            json={
                "message": "Add CI workflow for migration testing",
                "content": encoded,
            },
        )
        if resp.status_code in (200, 201):
            logger.info("✅ Added Actions workflow to %s", repo)
        elif resp.status_code == 422:
            logger.info("⏭️  Workflow already exists in %s", repo)
        else:
            logger.warning("⚠️  Could not add workflow to %s: %s", repo, resp.status_code)

    # ── Members ─────────────────────────────────────────────────────
    def invite_member(self, username: str, role: str = "member") -> bool:
        """Invite a GitHub user to the org."""
        # First check if already a member
        resp = self._get(f"/orgs/{self.org}/members/{username}")
        if resp.status_code == 204:
            logger.info("⏭️  %s is already a member of %s", username, self.org)
            return True

        resp = self._put(
            f"/orgs/{self.org}/memberships/{username}",
            json={"role": role},
        )
        if resp.status_code in (200, 201):
            state = resp.json().get("state", "unknown")
            logger.info("✅ Invited %s as %s (state: %s)", username, role, state)
            return True
        else:
            logger.error("❌ Failed to invite %s: %s %s",
                         username, resp.status_code, resp.text[:200])
            return False

    def add_outside_collaborator(self, username: str, repo: str) -> bool:
        """Add an outside collaborator to a specific repo."""
        resp = self._put(
            f"/repos/{self.org}/{repo}/collaborators/{username}",
            json={"permission": "push"},
        )
        if resp.status_code in (200, 201, 204):
            logger.info("✅ Added %s as outside collaborator on %s", username, repo)
            return True
        else:
            logger.error("❌ Failed to add collaborator %s: %s %s",
                         username, resp.status_code, resp.text[:200])
            return False

    # ── Cleanup ─────────────────────────────────────────────────────
    def cleanup_test_repos(self) -> None:
        """Delete all repos prefixed with 'test-'."""
        resp = self._get(f"/orgs/{self.org}/repos?per_page=100")
        if resp.status_code != 200:
            logger.error("Failed to list repos")
            return

        for repo in resp.json():
            if repo["name"].startswith("test-"):
                # Need to unarchive before deleting
                if repo.get("archived"):
                    self.session.patch(
                        f"{API}/repos/{self.org}/{repo['name']}",
                        json={"archived": False},
                        timeout=30,
                    )
                del_resp = self._delete(f"/repos/{self.org}/{repo['name']}")
                if del_resp.status_code == 204:
                    logger.info("🗑️  Deleted %s/%s", self.org, repo["name"])
                else:
                    logger.error("❌ Failed to delete %s: %s",
                                 repo["name"], del_resp.status_code)

    # ── Full setup ──────────────────────────────────────────────────
    def full_setup(
        self,
        invite_users: list[str] | None = None,
        collaborator_user: str | None = None,
    ) -> dict[str, Any]:
        """Run the complete test org setup."""
        logger.info("=" * 60)
        logger.info("Setting up test environment in org: %s", self.org)
        logger.info("=" * 60)

        # 1. Verify org
        if not self.verify_org():
            logger.error("Cannot proceed — org not accessible")
            sys.exit(1)

        # 2. Create repos
        logger.info("\n── Creating test repositories ──")
        repos = self.create_test_repos()
        time.sleep(2)  # Let GitHub catch up

        # 3. Add Actions workflows to some repos
        logger.info("\n── Adding GitHub Actions workflows ──")
        for repo in ["test-backend-api", "test-frontend-app", "test-shared-libs"]:
            if repo in repos:
                self.add_actions_workflow(repo)

        # 4. Invite members
        if invite_users:
            logger.info("\n── Inviting members ──")
            for user in invite_users:
                self.invite_member(user)

        # 5. Add outside collaborator
        if collaborator_user and "test-public-docs" in repos:
            logger.info("\n── Adding outside collaborator ──")
            self.add_outside_collaborator(collaborator_user, "test-public-docs")

        # 6. Summary
        summary = {
            "org": self.org,
            "repos_created": repos,
            "members_invited": invite_users or [],
            "outside_collaborator": collaborator_user,
        }

        logger.info("\n" + "=" * 60)
        logger.info("✅ Test environment ready!")
        logger.info("=" * 60)
        logger.info("Org          : %s", self.org)
        logger.info("Repos        : %d", len(repos))
        logger.info("Invitations  : %d", len(invite_users or []))
        logger.info("Collaborators: %s", collaborator_user or "none")
        logger.info("")
        logger.info("Next: edit config.yaml and run 'emu-migrate assess'")

        return summary


def main():
    parser = argparse.ArgumentParser(
        description="Set up a demo GitHub org for EMU migration testing"
    )
    parser.add_argument("--org", required=True, help="GitHub organization slug")
    parser.add_argument("--token", default=None, help="GitHub PAT (admin:org, repo, workflow), or set GH_TOKEN env var")
    parser.add_argument(
        "--invite",
        nargs="*",
        default=[],
        help="GitHub usernames to invite as members",
    )
    parser.add_argument(
        "--collaborator",
        default=None,
        help="GitHub username to add as outside collaborator",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete all test-* repos instead of creating them",
    )

    args = parser.parse_args()
    token = args.token or os.environ.get("GH_TOKEN")
    if not token:
        parser.error("A GitHub PAT is required via --token or GH_TOKEN env var")
    setup = GitHubSetup(token=token, org=args.org)

    if args.cleanup:
        logger.info("🗑️  Cleaning up test repos in %s ...", args.org)
        setup.cleanup_test_repos()
    else:
        setup.full_setup(
            invite_users=args.invite or None,
            collaborator_user=args.collaborator,
        )


if __name__ == "__main__":
    main()
