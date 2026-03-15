"""GitHub Enterprise Importer (GEI) CLI wrapper.

Calls `gh gei` subcommands via subprocess, streams output to Rich console,
and returns structured results.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from rich.table import Table

from ._console import console

logger = logging.getLogger(__name__)


# ── Data models ─────────────────────────────────────────────────────


class MigrationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RepoMigrationResult:
    repo: str
    status: MigrationStatus
    migration_id: str = ""
    error: str = ""
    duration_seconds: float = 0.0


@dataclass
class MigrationRun:
    source_org: str
    target_org: str
    dry_run: bool
    results: list[RepoMigrationResult] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.status == MigrationStatus.SUCCEEDED)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == MigrationStatus.FAILED)

    @property
    def total(self) -> int:
        return len(self.results)


@dataclass
class MannequinMapping:
    source_login: str
    target_login: str
    mannequin_id: str = ""
    mannequin_login: str = ""


# ── GEI wrapper ─────────────────────────────────────────────────────


class GEIClient:
    """Wrapper around the `gh gei` CLI extension."""

    def __init__(
        self,
        source_pat: str | None = None,
        target_pat: str | None = None,
    ):
        self._source_pat = source_pat
        self._target_pat = target_pat
        self._validate_install()

    # ── Installation checks ─────────────────────────────────────────

    def _validate_install(self) -> None:
        if not shutil.which("gh"):
            raise RuntimeError(
                "GitHub CLI (gh) not found on PATH. "
                "Install from https://cli.github.com/"
            )

    @staticmethod
    def is_installed() -> bool:
        """Check if gh and gh-gei extension are available."""
        if not shutil.which("gh"):
            return False
        try:
            result = subprocess.run(
                ["gh", "extension", "list"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return "gei" in result.stdout.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @staticmethod
    def install_extension() -> None:
        """Install the gh-gei extension."""
        console.print("[bold]Installing gh-gei extension…[/]")
        result = subprocess.run(
            ["gh", "extension", "install", "github/gh-gei"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            # Already installed is fine
            if "already installed" in result.stderr.lower():
                console.print("[dim]gh-gei already installed.[/]")
                return
            raise RuntimeError(f"Failed to install gh-gei: {result.stderr}")
        console.print("[green]gh-gei extension installed.[/]")

    def ensure_extension(self) -> None:
        """Install gh-gei if not already present."""
        if not self.is_installed():
            self.install_extension()

    # ── Core GEI subprocess ─────────────────────────────────────────

    def _run(
        self,
        args: list[str],
        env_extra: dict[str, str] | None = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess:
        """Run a `gh gei` command and return the result."""
        cmd = ["gh", "gei"] + args
        env = os.environ.copy()
        if self._source_pat:
            env["GH_PAT"] = self._source_pat
        if self._target_pat:
            env["GH_TARGET_PAT"] = self._target_pat
        if env_extra:
            env.update(env_extra)

        logger.info("Running: gh gei %s", " ".join(args))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
        if result.stdout:
            logger.debug("stdout: %s", result.stdout[:2000])
        if result.stderr:
            logger.debug("stderr: %s", result.stderr[:2000])
        return result

    # ── Repo migration ──────────────────────────────────────────────

    def migrate_repo(
        self,
        source_org: str,
        target_org: str,
        repo: str,
        target_repo: str | None = None,
        wait: bool = True,
    ) -> RepoMigrationResult:
        """Migrate a single repository."""
        import time

        target = target_repo or repo
        args = [
            "migrate-repo",
            "--github-source-org", source_org,
            "--source-repo", repo,
            "--github-target-org", target_org,
            "--target-repo", target,
        ]
        if wait:
            args.append("--wait")

        start = time.monotonic()
        try:
            result = self._run(args, timeout=1800)  # 30 min per repo
        except subprocess.TimeoutExpired:
            return RepoMigrationResult(
                repo=repo,
                status=MigrationStatus.FAILED,
                error="Migration timed out after 30 minutes.",
                duration_seconds=time.monotonic() - start,
            )
        elapsed = time.monotonic() - start

        if result.returncode == 0:
            migration_id = self._extract_migration_id(result.stdout + result.stderr)
            return RepoMigrationResult(
                repo=repo,
                status=MigrationStatus.SUCCEEDED,
                migration_id=migration_id,
                duration_seconds=elapsed,
            )
        else:
            return RepoMigrationResult(
                repo=repo,
                status=MigrationStatus.FAILED,
                error=result.stderr.strip() or result.stdout.strip(),
                duration_seconds=elapsed,
            )

    def migrate_repos(
        self,
        source_org: str,
        target_org: str,
        repos: list[str],
        dry_run: bool = True,
    ) -> MigrationRun:
        """Migrate a list of repositories sequentially."""
        run = MigrationRun(
            source_org=source_org,
            target_org=target_org,
            dry_run=dry_run,
        )

        if dry_run:
            console.print("[bold yellow]DRY RUN — validating repos only[/]\n")
            for repo in repos:
                console.print(f"  [dim]Would migrate:[/] {source_org}/{repo} → {target_org}/{repo}")
                run.results.append(
                    RepoMigrationResult(repo=repo, status=MigrationStatus.SKIPPED)
                )
            return run

        total = len(repos)
        for idx, repo in enumerate(repos, 1):
            console.print(f"\n[bold][{idx}/{total}][/] Migrating [cyan]{repo}[/] …")
            result = self.migrate_repo(source_org, target_org, repo)
            run.results.append(result)

            if result.status == MigrationStatus.SUCCEEDED:
                console.print(
                    f"  [green]✓[/] {repo} migrated in {result.duration_seconds:.1f}s"
                )
            else:
                console.print(f"  [red]✗[/] {repo} failed: {result.error[:200]}")

        return run

    # ── Mannequin reclaim ───────────────────────────────────────────

    def generate_mannequin_csv(
        self,
        target_org: str,
        output_path: str = "mannequins.csv",
    ) -> str:
        """Generate mannequin CSV for the target org."""
        args = [
            "generate-mannequin-csv",
            "--github-target-org", target_org,
            "--output", output_path,
        ]
        result = self._run(args)
        if result.returncode != 0:
            raise RuntimeError(f"Mannequin CSV generation failed: {result.stderr}")
        return output_path

    def reclaim_mannequins(
        self,
        target_org: str,
        csv_path: str,
    ) -> bool:
        """Run mannequin reclaim from a mapping CSV."""
        args = [
            "reclaim-mannequin",
            "--github-target-org", target_org,
            "--csv", csv_path,
        ]
        result = self._run(args, timeout=1800)
        if result.returncode != 0:
            console.print(f"[red]Mannequin reclaim failed:[/] {result.stderr}")
            return False
        console.print("[green]Mannequin reclaim completed.[/]")
        return True

    def save_mannequin_csv(
        self,
        mappings: list[MannequinMapping],
        output_dir: str = "reports",
    ) -> str:
        """Write a mannequin mapping CSV and return the path."""
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        csv_path = str(path / "mannequin-mapping.csv")

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["mannequin-user", "mannequin-id", "target-user"])
            for m in mappings:
                writer.writerow([m.mannequin_login or m.source_login, m.mannequin_id, m.target_login])

        console.print(f"[dim]Mannequin mapping saved to {csv_path}[/]")
        return csv_path

    def reclaim_mannequins_with_mapping(
        self,
        target_org: str,
        mappings: list[MannequinMapping],
        output_dir: str = "reports",
    ) -> bool:
        """Write a mapping CSV and run mannequin reclaim."""
        csv_path = self.save_mannequin_csv(mappings, output_dir)
        return self.reclaim_mannequins(target_org, csv_path)

    # ── Migration status ────────────────────────────────────────────

    def wait_for_migration(self, migration_id: str) -> subprocess.CompletedProcess:
        """Wait for a specific migration to complete."""
        args = ["wait-for-migration", "--migration-id", migration_id]
        return self._run(args, timeout=3600)

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_migration_id(output: str) -> str:
        """Try to extract a migration ID from GEI output."""
        for line in output.splitlines():
            lower = line.lower()
            if "migration id" in lower or "migration_id" in lower:
                # Common formats: "Migration ID: RM_xxx" or "migration_id: xxx"
                parts = line.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip()
            # GEI sometimes outputs just the ID on a line
            stripped = line.strip()
            if stripped.startswith("RM_"):
                return stripped
        return ""


# ── Reporting helpers ───────────────────────────────────────────────


def print_migration_summary(run: MigrationRun) -> None:
    """Print a Rich summary table of migration results."""
    table = Table(
        title=f"Migration: {run.source_org} → {run.target_org}",
        show_lines=True,
    )
    table.add_column("Repository", style="cyan")
    table.add_column("Status")
    table.add_column("Migration ID", style="dim")
    table.add_column("Duration", justify="right")
    table.add_column("Error", style="red", max_width=60)

    for r in run.results:
        status_style = {
            MigrationStatus.SUCCEEDED: "[green]succeeded[/]",
            MigrationStatus.FAILED: "[red]FAILED[/]",
            MigrationStatus.SKIPPED: "[yellow]skipped (dry-run)[/]",
            MigrationStatus.PENDING: "[dim]pending[/]",
            MigrationStatus.IN_PROGRESS: "[blue]in progress[/]",
        }
        table.add_row(
            r.repo,
            status_style.get(r.status, r.status.value),
            r.migration_id or "—",
            f"{r.duration_seconds:.1f}s" if r.duration_seconds else "—",
            r.error[:60] if r.error else "",
        )

    console.print(table)
    console.print(
        f"\n[bold]Total:[/] {run.total} | "
        f"[green]Succeeded:[/] {run.succeeded} | "
        f"[red]Failed:[/] {run.failed}"
    )


def save_migration_log(run: MigrationRun, output_dir: str = "reports") -> Path:
    """Save migration results to a JSON log file."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    log_path = path / "migration-log.json"

    data = {
        "source_org": run.source_org,
        "target_org": run.target_org,
        "dry_run": run.dry_run,
        "total": run.total,
        "succeeded": run.succeeded,
        "failed": run.failed,
        "repos": [
            {
                "repo": r.repo,
                "status": r.status.value,
                "migration_id": r.migration_id,
                "error": r.error,
                "duration_seconds": r.duration_seconds,
            }
            for r in run.results
        ],
    }

    log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    console.print(f"[dim]Migration log saved to {log_path}[/]")
    return log_path
