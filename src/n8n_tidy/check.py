"""Pre-commit / CI checks for workflow exports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .io import parse
from .normalize import dumps, normalize

__all__ = ["KINDS", "Problem", "check_text", "mask", "redact_text", "redact_value"]

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


def _secret_spans(text: str) -> list[tuple[int, int]]:
    """Spans of token-like strings; a span already reported by an earlier pattern is not reported again."""
    seen: list[tuple[int, int]] = []
    for pattern in _SECRET_PATTERNS:
        group = 1 if pattern.groups else 0
        for m in pattern.finditer(text):
            start, end = m.span(group)
            if any(start < e and s < end for s, e in seen):
                continue
            seen.append((start, end))
    return seen


def _find_secrets(text: str) -> list[str]:
    """Return masked tokens."""
    return [mask(text[s:e]) for s, e in _secret_spans(text)]


def _redact_plain(text: str) -> str:
    out, pos = [], 0
    for start, end in sorted(_secret_spans(text)):
        out.append(text[pos:start])
        out.append(mask(text[start:end]))
        pos = end
    out.append(text[pos:])
    return "".join(out)


def redact_text(text: str, *, expression: bool = False) -> str:
    """Replace token-like spans with their masked form (same patterns and masking as ``check``).

    With ``expression=True`` the text is an n8n expression body: closed ``{{ ... }}`` spans are left alone,
    exactly as ``check`` ignores them.
    """
    if not expression:
        return _redact_plain(text)
    out, pos = [], 0
    for m in _EXPRESSION_REF.finditer(text):
        out.append(_redact_plain(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_redact_plain(text[pos:]))
    return "".join(out)


def redact_value(value: Any) -> Any:
    """Redact every string inside a JSON-like value; keys are left untouched."""
    if isinstance(value, str):
        if value.startswith("="):
            return "=" + redact_text(value[1:], expression=True)
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value


def check_text(text: str, source: str, allow: Iterable[str] = (), *,
               keep_static_data: bool = False) -> list[Problem]:
    """Check one file's text. ``allow`` lists kinds to ignore (see :data:`KINDS`).

    ``keep_static_data`` compares against the output of ``normalize --keep-static-data``.
    """
    allowed = set(allow)
    unknown = allowed - set(KINDS)
    if unknown:
        raise ValueError(f"unknown check kind(s): {', '.join(sorted(unknown))}; choose from {', '.join(KINDS)}")
    workflows, is_array = parse(text, source)
    problems: list[Problem] = []

    if "not-normalized" not in allowed:
        keep_pin = "pin-data" in allowed
        normalized = [normalize(w, keep_pin_data=keep_pin, keep_static_data=keep_static_data) for w in workflows]
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
