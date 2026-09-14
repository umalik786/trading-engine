"""Run manifest. See docs/trading-engine-architecture.md P5 (§1) and §9.

Given the same data, config and seed, the engine must produce bit-identical
output, and every run records a manifest so a result can be traced back to
exactly the code and inputs that produced it. If the working tree is dirty,
the manifest says so explicitly -- a result recorded against a commit that
doesn't reflect the code that produced it is worse than no manifest at all.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from engine.core.types import require_utc


@dataclass(frozen=True)
class RunManifest:
    commit_hash: str
    working_tree_dirty: bool
    config_hash: str
    data_range_start: datetime
    data_range_end: datetime
    seed: int
    run_started_at: datetime  # UTC

    def __post_init__(self) -> None:
        require_utc("data_range_start", self.data_range_start)
        require_utc("data_range_end", self.data_range_end)
        require_utc("run_started_at", self.run_started_at)


def _git_commit_hash(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _git_working_tree_dirty(repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return bool(result.stdout.strip())


def hash_config_file(config_path: Path) -> str:
    return hashlib.sha256(config_path.read_bytes()).hexdigest()


def build_manifest(
    repo_root: Path,
    config_path: Path,
    data_range_start: datetime,
    data_range_end: datetime,
    seed: int,
) -> RunManifest:
    return RunManifest(
        commit_hash=_git_commit_hash(repo_root),
        working_tree_dirty=_git_working_tree_dirty(repo_root),
        config_hash=hash_config_file(config_path),
        data_range_start=data_range_start,
        data_range_end=data_range_end,
        seed=seed,
        run_started_at=datetime.now(UTC),
    )
