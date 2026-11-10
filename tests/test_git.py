import subprocess
import sys

from conftest import FIXTURES, copy_fixture
from n8n_tidy.cli import main

COMMAND = f"{sys.executable} -m n8n_tidy"


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def test_install_git_local_only(isolated_git, capsys):
    repo, global_cfg = isolated_git
    assert main(["install-git", "--command", COMMAND, "--pattern", "workflows/*.json", "--dry-run"]) == 0
    assert "(dry run)" in capsys.readouterr().out
    assert not (repo / ".gitattributes").exists()

    for _ in range(2):  # running twice must not duplicate anything
        assert main(["install-git", "--command", COMMAND, "--pattern", "workflows/*.json"]) == 0
    capsys.readouterr()
    assert git(repo, "config", "--local", "--get", "diff.n8n.textconv").strip() == f"{COMMAND} textconv"
    assert f"{COMMAND} diff" in git(repo, "config", "--local", "--get", "difftool.n8n-tidy.cmd")
    attrs = (repo / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert attrs == ["workflows/*.json diff=n8n"]
    assert git(repo, "config", "--local", "--get-all", "diff.n8n.textconv").count("\n") == 1
    assert global_cfg.read_text(encoding="utf-8") == ""  # the isolated global config stayed empty

    assert main(["uninstall-git"]) == 0
    capsys.readouterr()
    assert not (repo / ".gitattributes").exists()
    assert subprocess.run(["git", "config", "--local", "--get", "diff.n8n.textconv"], cwd=repo).returncode == 1


def test_install_outside_repo_is_a_friendly_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert main(["install-git"]) == 2
    assert "git init" in capsys.readouterr().err


def test_git_diff_uses_textconv(isolated_git, capsys):
    repo, _ = isolated_git
    assert main(["install-git", "--command", COMMAND]) == 0
    capsys.readouterr()
    target = copy_fixture("export-v1.json", repo / "wf.json")
    git(repo, "add", ".gitattributes", "wf.json")
    copy_fixture("export-v2.json", target)
    out = git(repo, "diff")
    assert "+  Always answer in Korean." in out
    assert "versionId" not in out
    assert "someone@example.com" not in out


def test_diff_against_revision(isolated_git, capsys):
    repo, _ = isolated_git
    target = copy_fixture("export-v1.json", repo / "wf.json")
    git(repo, "add", "wf.json")
    git(repo, "commit", "-q", "-m", "add workflow")
    copy_fixture("export-v2.json", target)
    assert main(["diff", "--rev", "HEAD", "wf.json"]) == 0
    out = capsys.readouterr().out
    assert "node renamed" in out and "+Always answer in Korean." in out

    assert main(["diff", "--rev", "no-such-rev", "wf.json"]) == 2
    assert "cannot read" in capsys.readouterr().err
    assert main(["diff", "--rev=--oops", "wf.json"]) == 2
