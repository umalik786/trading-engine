import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.core.manifest import RunManifest, build_manifest, hash_config_file


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=repo_root, check=True, capture_output=True
    )


def _commit_all(repo_root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_root, check=True, capture_output=True)


def _current_head(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


class TestManifest:
    def test_commit_hash_and_clean_tree(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        (tmp_path / "tracked.txt").write_text("v1", encoding="utf-8")
        config_path = tmp_path / "config.yaml"
        config_path.write_text("profile: test\n", encoding="utf-8")
        # config.yaml is committed too -- otherwise it would be an untracked
        # file and the tree would read as dirty for the wrong reason.
        _commit_all(tmp_path, "initial commit")
        expected_hash = _current_head(tmp_path)

        manifest = build_manifest(
            repo_root=tmp_path,
            config_path=config_path,
            data_range_start=datetime(2020, 1, 1, tzinfo=UTC),
            data_range_end=datetime(2024, 1, 1, tzinfo=UTC),
            seed=42,
        )

        assert manifest.commit_hash == expected_hash
        assert manifest.working_tree_dirty is False
        assert manifest.config_hash == hash_config_file(config_path)
        assert manifest.seed == 42
        assert manifest.run_started_at.tzinfo is not None

    def test_dirty_tree_is_flagged(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        tracked = tmp_path / "tracked.txt"
        tracked.write_text("v1", encoding="utf-8")
        _commit_all(tmp_path, "initial commit")
        clean_commit_hash = _current_head(tmp_path)

        # Modify a tracked file without committing -- the tree is now dirty,
        # but HEAD hasn't moved.
        tracked.write_text("v2", encoding="utf-8")

        config_path = tmp_path / "config.yaml"
        config_path.write_text("profile: test\n", encoding="utf-8")

        manifest = build_manifest(
            repo_root=tmp_path,
            config_path=config_path,
            data_range_start=datetime(2020, 1, 1, tzinfo=UTC),
            data_range_end=datetime(2024, 1, 1, tzinfo=UTC),
            seed=7,
        )

        assert manifest.working_tree_dirty is True
        assert manifest.commit_hash == clean_commit_hash

    def test_naive_data_range_start_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            RunManifest(
                commit_hash="abc123",
                working_tree_dirty=False,
                config_hash="deadbeef",
                data_range_start=datetime(2020, 1, 1),  # noqa: DTZ001 -- naivety is what's under test
                data_range_end=datetime(2024, 1, 1, tzinfo=UTC),
                seed=1,
                run_started_at=datetime.now(UTC),
            )
