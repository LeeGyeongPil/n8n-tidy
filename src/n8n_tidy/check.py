"""Pre-commit / CI checks for workflow exports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .io import parse
from .normalize import dumps, normalize

__all__ = ["KINDS", "Problem", "check_text", "mask"]

KINDS = ("not-normalized", "pin-data", "instance-info", "secret-suspect")

# Shapes of well-known credentials. These are heuristics, not a replacement for a secret scanner.
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer\s+([A-Za-z0-9._~+/=-]{20,})"),
)


@dataclass
class Problem:
    """One finding: where it is and what kind it is."""

    file: str
    node: str
    path: str
    kind: str
    detail: str = ""

    def format(self) -> str:
        text = f"{self.file}: {self.node or '-'} > {self.path or '-'}: {self.kind}"
        return f"{text} ({self.detail})" if self.detail else text


def mask(token: str) -> str:
    """Show only the first 4 characters so the report itself never leaks the secret."""
    return token[:4] + "****"


def _walk_strings(value: Any, path: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _walk_strings(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _walk_strings(v, f"{path}[{i}]")


_EXPRESSION_REF = re.compile(r"\{\{.*?\}\}", re.DOTALL)


def _strip_expression_refs(text: str) -> str:
    """Blank out closed ``{{ ... }}`` spans; an unclosed ``{{`` is left as-is (checked conservatively)."""
    return _EXPRESSION_REF.sub(" ", text)


def _find_secrets(text: str) -> list[str]:
    found = []
    for pattern in _SECRET_PATTERNS:
        for m in pattern.finditer(text):
            found.append(mask(m.group(1) if pattern.groups else m.group(0)))
    return found


def check_text(text: str, source: str, allow: Iterable[str] = ()) -> list[Problem]:
    """Check one file's text. ``allow`` lists kinds to ignore (see :data:`KINDS`)."""
    allowed = set(allow)
    unknown = allowed - set(KINDS)
    if unknown:
        raise ValueError(f"unknown check kind(s): {', '.join(sorted(unknown))}; choose from {', '.join(KINDS)}")
    workflows, is_array = parse(text, source)
    problems: list[Problem] = []

    if "not-normalized" not in allowed:
        keep_pin = "pin-data" in allowed
        normalized = [normalize(w, keep_pin_data=keep_pin) for w in workflows]
        expected = dumps(normalized if is_array else normalized[0])
        if expected != text:
            problems.append(Problem(source, "", "", "not-normalized", "run `n8n-tidy normalize`"))

    for wf in workflows:
        if "pin-data" not in allowed and wf.get("pinData"):
            for node in wf["pinData"]:
                problems.append(Problem(source, str(node), f"pinData.{node}", "pin-data",
                                        "pinned test data may contain real personal data"))
        if "instance-info" not in allowed:
            if wf.get("shared"):
                problems.append(Problem(source, "", "shared", "instance-info", "owner/project of the source instance"))
            meta = wf.get("meta")
            if isinstance(meta, dict) and meta.get("instanceId"):
                problems.append(Problem(source, "", "meta.instanceId", "instance-info", "id of the source instance"))
        if "secret-suspect" not in allowed:
            for node in wf.get("nodes", []):
                for path, value in _walk_strings(node.get("parameters", {}), "parameters"):
                    if value.startswith("="):  # n8n expression: check only the text outside {{ ... }}
                        value = _strip_expression_refs(value[1:])
                    for masked in _find_secrets(value):
                        problems.append(Problem(source, str(node.get("name", "")), path, "secret-suspect",
                                                f"looks like a token: {masked}"))
    return problems
