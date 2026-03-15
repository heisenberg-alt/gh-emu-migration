"""Unit tests for core pure-logic modules (no network required)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from emu_migration.assessment import STATIC_RISKS, _run_automated_checks
from emu_migration.config import load_config
from emu_migration.emu_migration import (
    build_emu_migration_plan,
    generate_gei_script,
    generate_mannequin_mapping,
)
from emu_migration.models import (
    AssessmentReport,
    MigrationPhase,
    OrgMember,
    RepoInfo,
)
from emu_migration.report import generate_markdown_report
from emu_migration.sso_migration import build_sso_switch_plan, validate_sso_readiness


# ── Fixtures ────────────────────────────────────────────────────────

VALID_CFG = {
    "github": {
        "enterprise": "test-ent",
        "organization": "test-org",
        "token": "ghp_test",
    },
    "entra_id": {
        "tenant_id": "aaaa-bbbb-cccc",
        "client_id": "1111-2222-3333",
        "client_secret": "secret",
        "app_display_name": "GitHub EMU",
    },
    "adfs": {
        "entity_id": "https://adfs.example.com/trust",
        "sso_url": "https://adfs.example.com/adfs/ls/",
    },
    "emu": {
        "short_code": "testco",
        "owners_group": "GH-Owners",
        "members_group": "GH-Members",
    },
    "migration": {
        "dry_run": True,
        "report_output": "reports/",
    },
}


def _make_report() -> AssessmentReport:
    members = [
        OrgMember(login="alice", github_id=1, saml_identity="alice@ex.com", role="admin"),
        OrgMember(login="bob", github_id=2, saml_identity=None, role="member"),
        OrgMember(login="svc-ci", github_id=3, saml_identity="svc@ex.com", role="member"),
    ]
    repos = [
        RepoInfo(name="repo-a", full_name="org/repo-a", private=True, fork=False,
                 archived=False, size_kb=100, default_branch="main", has_actions=True),
        RepoInfo(name="old-thing", full_name="org/old-thing", private=False, fork=False,
                 archived=True, size_kb=5000, default_branch="master"),
    ]
    return AssessmentReport(
        enterprise="test-ent",
        organization="test-org",
        timestamp="2025-01-01T00:00:00+00:00",
        members=members,
        repos=repos,
        risks=[copy.copy(r) for r in STATIC_RISKS],
        total_members=len(members),
        total_repos=len(repos),
        outside_collaborators=1,
        saml_configured=True,
    )


# ── Config tests ────────────────────────────────────────────────────

class TestConfig:
    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_valid_config(self, tmp_path: Path):
        import yaml

        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump(VALID_CFG), encoding="utf-8")
        result = load_config(cfg_path)
        assert result["github"]["organization"] == "test-org"

    def test_load_placeholder_rejected(self, tmp_path: Path):
        import yaml

        bad_cfg = {**VALID_CFG, "github": {**VALID_CFG["github"], "token": "REPLACE_ME"}}
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump(bad_cfg), encoding="utf-8")
        with pytest.raises(ValueError, match="Missing or placeholder"):
            load_config(cfg_path)


# ── Plan structure tests ────────────────────────────────────────────

class TestSSOPlan:
    def test_step_count(self):
        plan = build_sso_switch_plan(VALID_CFG)
        assert len(plan.steps) == 10

    def test_all_steps_sso_phase(self):
        plan = build_sso_switch_plan(VALID_CFG)
        for step in plan.steps:
            assert step.phase == MigrationPhase.SSO_SWITCH

    def test_steps_ordered(self):
        plan = build_sso_switch_plan(VALID_CFG)
        orders = [s.order for s in plan.steps]
        assert orders == sorted(orders)


class TestEMUPlan:
    def test_step_count(self):
        plan = build_emu_migration_plan(VALID_CFG)
        assert len(plan.steps) == 14

    def test_dry_run_flag(self):
        plan = build_emu_migration_plan(VALID_CFG)
        assert plan.dry_run is True

    def test_steps_ordered(self):
        plan = build_emu_migration_plan(VALID_CFG)
        orders = [s.order for s in plan.steps]
        assert orders == sorted(orders)


# ── SSO readiness validation ────────────────────────────────────────

class TestSSOReadiness:
    def test_valid_config_no_issues(self):
        issues = validate_sso_readiness(VALID_CFG)
        assert issues == []

    def test_placeholder_tenant(self):
        cfg = {**VALID_CFG, "entra_id": {**VALID_CFG["entra_id"], "tenant_id": "0000-placeholder"}}
        issues = validate_sso_readiness(cfg)
        assert any("tenant_id" in i for i in issues)

    def test_missing_adfs_entity(self):
        cfg = {**VALID_CFG, "adfs": {}}
        issues = validate_sso_readiness(cfg)
        assert any("ADFS" in i for i in issues)


# ── GEI script generation ──────────────────────────────────────────

class TestGEIScript:
    def test_script_contains_repos(self):
        script = generate_gei_script(["repo-a", "repo-b"], "src-org", "tgt-org")
        assert "repo-a" in script
        assert "repo-b" in script
        assert "gh gei migrate-repo" in script

    def test_script_uses_shlex_quoting(self):
        script = generate_gei_script(["has space"], "org with space", "tgt")
        # shlex.quote wraps values containing spaces in single quotes
        assert "'has space'" in script
        assert "'org with space'" in script

    def test_script_is_bash(self):
        script = generate_gei_script(["r1"], "s", "t")
        assert script.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in script


# ── Mannequin mapping ──────────────────────────────────────────────

class TestMannequinMapping:
    def test_basic_mapping(self):
        members = [{"login": "alice"}, {"login": "bob"}]
        result = generate_mannequin_mapping(members, "co")
        assert len(result) == 2
        assert result[0] == {"source": "alice", "target": "alice_co"}
        assert result[1] == {"source": "bob", "target": "bob_co"}

    def test_empty_login_skipped(self):
        members = [{"login": "alice"}, {"login": ""}, {"name": "no-login"}]
        result = generate_mannequin_mapping(members, "co")
        assert len(result) == 1


# ── Risk assessment automated checks ───────────────────────────────

class TestAutomatedChecks:
    def test_static_risks_not_mutated(self):
        """Verify that running checks doesn't corrupt the global catalogue."""
        original_descriptions = {r.id: r.description for r in STATIC_RISKS}
        report = _make_report()
        _run_automated_checks(report, VALID_CFG)
        for r in STATIC_RISKS:
            assert r.description == original_descriptions[r.id], (
                f"STATIC_RISKS[{r.id}].description was mutated"
            )

    def test_unlinked_member_detected(self):
        report = _make_report()
        _run_automated_checks(report, VALID_CFG)
        sso002 = next(r for r in report.risks if r.id == "SSO-002")
        assert sso002.check_passed is False  # bob has no SAML identity

    def test_service_account_detected(self):
        report = _make_report()
        _run_automated_checks(report, VALID_CFG)
        sso004 = next(r for r in report.risks if r.id == "SSO-004")
        assert sso004.check_passed is False  # svc-ci matches service pattern


# ── Markdown report generation ──────────────────────────────────────

class TestMarkdownReport:
    def test_report_structure(self):
        report = _make_report()
        _run_automated_checks(report, VALID_CFG)
        sso_plan = build_sso_switch_plan(VALID_CFG)
        emu_plan = build_emu_migration_plan(VALID_CFG)
        md = generate_markdown_report(report, sso_plan, emu_plan)

        assert "# GitHub Enterprise Migration Report" in md
        assert "## Risk Assessment" in md
        assert "## Phase 1:" in md
        assert "## Phase 2:" in md

    def test_pipe_in_login_escaped(self):
        report = _make_report()
        report.members[0].login = "user|pipe"
        report.members[0].email = "a|b@c.com"
        _run_automated_checks(report, VALID_CFG)
        sso_plan = build_sso_switch_plan(VALID_CFG)
        emu_plan = build_emu_migration_plan(VALID_CFG)
        md = generate_markdown_report(report, sso_plan, emu_plan)

        # Pipes should be escaped to not break the table
        assert "user\\|pipe" in md
        assert "a\\|b@c.com" in md
