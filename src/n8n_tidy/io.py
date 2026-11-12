"""Reading and writing n8n workflow export files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "TidyError",
    "NotAWorkflowError",
    "InvalidJSONError",
    "is_workflow",
    "parse",
    "load",
    "iter_json_files",
    "write_text",
]

_SKIP_DIRS = {".git", "node_modules", ".venv"}


class TidyError(Exception):
    """Base class for errors that carry a user-facing message.

    ``str(exc)`` is always the English message. ``code`` and ``params`` (optional) let the command
    line render the same error in another language; library users can ignore them.
    """

    def __init__(self, message: str, *, code: str | None = None, params: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.params = dict(params or {})


class NotAWorkflowError(TidyError, ValueError):
    """The JSON is valid but is not an n8n workflow export."""


class InvalidJSONError(TidyError, ValueError):
    """The file is not valid JSON."""


def is_workflow(obj: Any) -> bool:
    """True when ``obj`` looks like one n8n workflow (``nodes`` list + ``connections`` object)."""
    return isinstance(obj, dict) and isinstance(obj.get("nodes"), list) and isinstance(obj.get("connections"), dict)


def parse(text: str, source: str = "<input>") -> tuple[list[dict], bool]:
    """Parse export text into ``(workflows, is_array)``.

    ``n8n export:workflow --all`` writes an array; ``--separate``/``--backup`` write one object per file.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidJSONError(
            f"{source}: not valid JSON ({exc}). Re-export the workflow or fix the file.",
            code="invalid_json", params={"source": source, "detail": str(exc)},
        ) from exc
    if isinstance(data, list):
        if data and all(is_workflow(item) for item in data):
            return data, True
    elif is_workflow(data):
        return [data], False
    raise NotAWorkflowError(
        f"{source}: not an n8n workflow export (expected an object or array with 'nodes' and 'connections').",
        code="not_workflow", params={"source": source},
    )


def load(path: str | Path) -> tuple[list[dict], bool]:
    """Read and parse a workflow export file."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TidyError(f"{p}: file not found.", code="file_not_found", params={"path": str(p)}) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise TidyError(
            f"{p}: cannot read as UTF-8 text ({exc}).", code="cannot_read", params={"path": str(p), "detail": str(exc)}
        ) from exc
    return parse(text, str(p))


def iter_json_files(paths: Iterable[str | Path]) -> list[Path]:
    """Expand files and folders (recursive ``*.json``) into a sorted, de-duplicated list."""
    found: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            candidates = sorted(
                f for f in p.rglob("*.json") if f.is_file() and not (_SKIP_DIRS & set(f.relative_to(p).parts))
            )
        elif p.is_file():
            candidates = [p]
        else:
            raise TidyError(f"{p}: path not found.", code="path_not_found", params={"path": str(p)})
        for c in candidates:
            key = c.resolve()
            if key not in seen:
                seen.add(key)
                found.append(c)
    return found


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text with LF newlines."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
