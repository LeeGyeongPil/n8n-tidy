"""Git helpers: read a file at a revision, install/uninstall the diff driver (local config only)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .io import TidyError

__all__ = ["GitError", "show_revision", "install", "uninstall", "DRIVER", "DIFFTOOL"]

DRIVER = "n8n"
DIFFTOOL = "n8n-tidy"
_TIMEOUT = 120


class GitError(TidyError):
    """A git command failed."""


def _git(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", timeout=_TIMEOUT)
    except FileNotFoundError as exc:
        raise GitError("git was not found on PATH. Install git first.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {' '.join(args)} timed out after {_TIMEOUT}s.") from exc
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def show_revision(rev: str, path: str | Path) -> str:
    """Return the content of ``path`` (relative to the cwd) at ``rev``."""
    if rev.startswith("-"):
        raise GitError(f"invalid revision {rev!r}: must not start with '-'.")
    p = Path(path).resolve()
    proc = _git(["show", f"{rev}:./{p.name}"], p.parent, check=False)
    if proc.returncode != 0:
        raise GitError(
            f"cannot read {path} at {rev}: {proc.stderr.strip()}. "
            "Check that the revision exists and the file is tracked there."
        )
    return proc.stdout


def _toplevel(cwd: Path) -> Path:
    proc = _git(["rev-parse", "--show-toplevel"], cwd, check=False)
    if proc.returncode != 0:
        raise GitError("not inside a git repository. Run `git init` first, then re-run install-git.")
    return Path(proc.stdout.strip())


def _attr_line(pattern: str) -> str:
    return f"{pattern} diff={DRIVER}"


def install(cwd: Path, *, pattern: str = "*.json", command: str = "n8n-tidy", dry_run: bool = False) -> list[str]:
    """Register the textconv/difftool drivers in the repository's local config and ``.gitattributes``.

    Returns the lines describing what was (or, with ``dry_run``, would be) written.
    Never touches the global or system git config.
    """
    if not pattern.strip() or any(ch in pattern for ch in "\n\r"):
        raise TidyError("--pattern must be a non-empty single-line glob such as 'workflows/**/*.json'.")
    if not command.strip():
        raise TidyError("--command must not be empty.")
    root = _toplevel(cwd)
    settings = [
        (f"diff.{DRIVER}.textconv", f"{command} textconv"),
        (f"diff.{DRIVER}.cachetextconv", "true"),
        (f"difftool.{DIFFTOOL}.cmd", f'{command} diff "$LOCAL" "$REMOTE"'),
    ]
    attr_file = root / ".gitattributes"
    line = _attr_line(pattern)
    existing = attr_file.read_text(encoding="utf-8").splitlines() if attr_file.exists() else []
    report = [f".gitattributes: {line}"] + [f"git config --local {k} {v!r}" for k, v in settings]
    if dry_run:
        return ["(dry run) " + r for r in report]
    if line not in existing:
        existing.append(line)
        attr_file.write_text("\n".join(existing) + "\n", encoding="utf-8")
    for key, value in settings:
        _git(["config", "--local", key, value], root)
    return report


def uninstall(cwd: Path) -> list[str]:
    """Remove what :func:`install` wrote (only lines ending in ``diff=n8n`` and the two config sections)."""
    root = _toplevel(cwd)
    done = []
    attr_file = root / ".gitattributes"
    if attr_file.exists():
        lines = attr_file.read_text(encoding="utf-8").splitlines()
        kept = [ln for ln in lines if not ln.rstrip().endswith(f" diff={DRIVER}")]
        if kept != lines:
            done.append(".gitattributes: removed diff=n8n lines")
            if kept:
                attr_file.write_text("\n".join(kept) + "\n", encoding="utf-8")
            else:
                attr_file.unlink()
    for section in (f"diff.{DRIVER}", f"difftool.{DIFFTOOL}"):
        if _git(["config", "--local", "--remove-section", section], root, check=False).returncode == 0:
            done.append(f"git config --local: removed [{section}]")
    return done
