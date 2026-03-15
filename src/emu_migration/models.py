"""Shared data models for the migration POC."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class MigrationPhase(str, Enum):
    ASSESSMENT = "assessment"
    SSO_SWITCH = "sso_switch"
    EMU_MIGRATION = "emu_migration"
    VALIDATION = "validation"


@dataclass
class Risk:
    id: str
    phase: MigrationPhase
    severity: Severity
    title: str
    description: str
    mitigation: str
    automated_check: bool = False
    check_passed: Optional[bool] = None


@dataclass
class OrgMember:
    login: str
    github_id: int
    email: Optional[str] = None
    name: Optional[str] = None
    role: str = "member"  # "admin" | "member"
    has_2fa: bool = False
    saml_identity: Optional[str] = None


@dataclass
class RepoInfo:
    name: str
    full_name: str
    private: bool
    fork: bool
    archived: bool
    size_kb: int
    default_branch: str
    has_actions: bool = False


@dataclass
class AssessmentReport:
    """Full pre-migration assessment."""
    enterprise: str
    organization: str
    timestamp: str
    members: list[OrgMember] = field(default_factory=list)
    repos: list[RepoInfo] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    total_members: int = 0
    total_repos: int = 0
    outside_collaborators: int = 0
    saml_configured: bool = False
    emu_ready: bool = False


@dataclass
class MigrationStep:
    order: int
    phase: MigrationPhase
    title: str
    description: str
    manual: bool  # True = requires human action
    status: str = "pending"  # pending | running | done | skipped | failed
    output: str = ""


@dataclass
class MigrationPlan:
    steps: list[MigrationStep] = field(default_factory=list)
    dry_run: bool = True
