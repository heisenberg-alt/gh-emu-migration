"""Thin wrapper around GitHub REST & GraphQL APIs."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_API = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"


class GitHubClient:
    """Authenticated GitHub API client."""

    def __init__(self, token: str, api_url: str = DEFAULT_API):
        self._api = api_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    # ── REST helpers ────────────────────────────────────────────────
    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self._api}{path}"
        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get_paginated(self, path: str, params: dict | None = None) -> list[Any]:
        """Auto-paginate a GitHub list endpoint."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        results: list[Any] = []
        url = f"{self._api}{path}"
        while url:
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            results.extend(resp.json())
            url = resp.links.get("next", {}).get("url")
            params = {}  # params are baked into next-link
        return results

    # ── GraphQL helper ──────────────────────────────────────────────
    def graphql(self, query: str, variables: dict | None = None) -> dict:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = self._session.post(GRAPHQL_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            logger.warning("GraphQL errors: %s", data["errors"])
        return data

    # ── Organization ────────────────────────────────────────────────
    def get_org(self, org: str) -> dict:
        return self._get(f"/orgs/{org}")

    def get_org_members(self, org: str) -> list[dict]:
        return self._get_paginated(f"/orgs/{org}/members")

    def get_org_member_detail(self, org: str, username: str) -> dict:
        return self._get(f"/orgs/{org}/memberships/{username}")

    def get_org_repos(self, org: str) -> list[dict]:
        return self._get_paginated(f"/orgs/{org}/repos", {"type": "all"})

    def get_outside_collaborators(self, org: str) -> list[dict]:
        return self._get_paginated(f"/orgs/{org}/outside_collaborators")

    def get_pending_invitations(self, org: str) -> list[dict]:
        return self._get_paginated(f"/orgs/{org}/invitations")

    # ── SAML (GraphQL – Enterprise Cloud) ───────────────────────────
    def get_saml_identities(self, org: str, first: int = 100) -> list[dict]:
        """Fetch all SAML identity mappings via GraphQL (cursor-paginated)."""
        query = """
        query($org: String!, $first: Int!, $after: String) {
          organization(login: $org) {
            samlIdentityProvider {
              externalIdentities(first: $first, after: $after) {
                pageInfo {
                  hasNextPage
                  endCursor
                }
                edges {
                  node {
                    guid
                    samlIdentity {
                      nameId
                    }
                    user {
                      login
                    }
                  }
                }
              }
            }
          }
        }
        """
        all_nodes: list[dict] = []
        cursor: str | None = None
        while True:
            variables: dict = {"org": org, "first": first}
            if cursor:
                variables["after"] = cursor
            data = self.graphql(query, variables)
            provider = (
                data.get("data", {})
                .get("organization", {})
                .get("samlIdentityProvider")
            )
            if not provider:
                break
            identities = provider.get("externalIdentities", {})
            edges = identities.get("edges", [])
            all_nodes.extend(e["node"] for e in edges)
            page_info = identities.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
        return all_nodes

    # ── Enterprise (for EMU readiness) ──────────────────────────────
    def get_enterprise_info(self, enterprise_slug: str) -> dict:
        query = """
        query($slug: String!) {
          enterprise(slug: $slug) {
            slug
            name
            ownerInfo {
              admins(first: 5) { totalCount }
              members(first: 5) { totalCount }
            }
          }
        }
        """
        return self.graphql(query, {"slug": enterprise_slug})

    # ── Repo detail helpers ─────────────────────────────────────────
    def get_repo_branch_protections(self, owner: str, repo: str) -> list[dict]:
        try:
            return self._get_paginated(f"/repos/{owner}/{repo}/branches")
        except requests.HTTPError:
            return []

    def get_repo_actions_workflows(self, owner: str, repo: str) -> list[dict]:
        try:
            data = self._get(f"/repos/{owner}/{repo}/actions/workflows")
            return data.get("workflows", [])
        except requests.HTTPError:
            return []
