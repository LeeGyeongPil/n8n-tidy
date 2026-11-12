"""Shared test helpers: fixture paths and a git environment isolated from the user's config."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fx() -> Path:
    return FIXTURES


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def isolated_git(tmp_path, monkeypatch):
    """A fresh git repo in tmp_path; global/system git config are replaced by an empty file."""
    global_cfg = tmp_path / "global-gitconfig"
    global_cfg.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key, value in {
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
    }.items():
        monkeypatch.setenv(key, value)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    monkeypatch.chdir(repo)
    return repo, global_cfg


def copy_fixture(name: str, dest: Path) -> Path:
    shutil.copyfile(FIXTURES / name, dest)
    return dest


@pytest.fixture(autouse=True)
def _english_by_default(monkeypatch):
    """Pin the output language so the host environment cannot change message wording."""
    monkeypatch.setenv("N8N_TIDY_LANG", "en")
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
