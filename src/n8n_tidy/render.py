"""Output formats: text, markdown, json, and the line-oriented review view used by textconv."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from .diff import Change, _edges, edge_text
from .normalize import normalize

__all__ = ["render_text", "render_md", "render_json", "review_view", "describe", "pin_data_warnings"]

_GREEN, _RED, _CYAN, _RESET = "\033[32m", "\033[31m", "\033[36m", "\033[0m"


def _fmt(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def pin_data_warnings(a_docs: list[dict], b_docs: list[dict]) -> list[str]:
    """``pinData`` is dropped by normalization, so say so instead of silently ignoring it."""
    warnings = []
    for label, docs in (("A", a_docs), ("B", b_docs)):
        if any(w.get("pinData") for w in docs):
            warnings.append(f"pinData present in {label} (not compared; run `n8n-tidy check` to see where)")
    return warnings


def describe(c: Change) -> str:
    """One human-readable line for a change (the text diff body is rendered separately)."""
    if c.kind == "rename":
        return f"node renamed: {c.before} -> {c.after}"
    if c.kind == "added":
        return f"node added: {c.node} [{c.after}]"
    if c.kind == "removed":
        return f"node removed: {c.node} [{c.before}]"
    if c.kind == "layout":
        return f"{c.node}: moved {_fmt(c.before)} -> {_fmt(c.after)}  (layout only)"
    if c.kind == "type":
        return f"{c.node}: type {c.before} -> {c.after}"
    if c.kind == "disabled":
        return f"{c.node}: disabled {_fmt(c.before)} -> {_fmt(c.after)}"
    if c.kind == "edge":
        verb = "added" if c.before is None else "removed"
        return f"edge {verb}: {c.path}"
    if c.kind == "workflow":
        return f"workflow {c.path}: {c.before or c.after}"
    if c.kind == "text":
        return f"{c.node}: {c.path} (text changed)"
    if c.kind == "field":
        return f"workflow: {c.path}: {_fmt(c.before)} -> {_fmt(c.after)}"
    return f"{c.node}: {c.path}: {_fmt(c.before)} -> {_fmt(c.after)}"


def _color_diff_line(line: str) -> str:
    if line.startswith("+"):
        return f"{_GREEN}{line}{_RESET}"
    if line.startswith("-"):
        return f"{_RED}{line}{_RESET}"
    if line.startswith("@@"):
        return f"{_CYAN}{line}{_RESET}"
    return line


def render_text(changes: list[Change], warnings: list[str], a_label: str, b_label: str,
                *, color: bool = False, multi: bool = False) -> str:
    lines = [f"n8n-tidy diff: {a_label} -> {b_label}"]
    lines += [f"! {w}" for w in warnings]
    if not changes:
        lines.append("No semantic changes.")
    for c in changes:
        prefix = f"[{c.workflow}] " if multi and c.workflow else ""
        lines.append(f"~ {prefix}{describe(c)}")
        if c.text_diff:
            for raw in c.text_diff.split("\n"):
                lines.append("    " + (_color_diff_line(raw) if color else raw))
    return "\n".join(lines) + "\n"


def render_md(changes: list[Change], warnings: list[str], a_label: str, b_label: str, *, multi: bool = False) -> str:
    lines = [f"## n8n-tidy diff: `{a_label}` -> `{b_label}`", ""]
    lines += [f"> **Warning:** {w}" for w in warnings]
    if warnings:
        lines.append("")
    if not changes:
        lines.append("No semantic changes.")
    # Group by node (workflow-level and connection changes get their own sections).
    sections: dict[str, list[Change]] = {}
    for c in changes:
        if c.kind in ("field", "workflow"):
            title = "Workflow"
        elif c.kind == "edge":
            title = "Connections"
        else:
            title = c.node or "Workflow"
        if multi and c.workflow:
            title = f"{c.workflow} / {title}"
        sections.setdefault(title, []).append(c)
    for title, items in sections.items():
        lines += [f"### {title}", ""]
        for c in items:
            lines.append(f"- {describe(c)}")
            if c.text_diff:
                lines += ["", "```diff", c.text_diff, "```", ""]
        if lines[-1] != "":
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def render_json(changes: list[Change], warnings: list[str], a_label: str, b_label: str) -> str:
    payload = {
        "a": a_label,
        "b": b_label,
        "warnings": warnings,
        "changes": [dataclasses.asdict(c) for c in changes],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _value_lines(path: str, value: Any) -> list[str]:
    if isinstance(value, str) and "\n" in value:
        return [f"{path}: |"] + ["  " + line for line in value.split("\n")]
    return [f"{path}: {_fmt(value)}"]


def _flatten(value: Any, prefix: str, out: list[tuple[str, Any]]) -> None:
    if isinstance(value, dict) and value:
        for key in sorted(value):
            _flatten(value[key], f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(value, list) and value:
        for i, item in enumerate(value):
            _flatten(item, f"{prefix}[{i}]", out)
    else:
        out.append((prefix, value))


def _review_one(wf: dict) -> list[str]:
    wf = normalize(wf)
    lines = [f"workflow: {wf.get('name', '')}  (id {wf.get('id', '-')})"]
    top: list[tuple[str, Any]] = []
    for key in sorted(set(wf) - {"nodes", "connections", "name", "id"}):
        _flatten(wf[key], key, top)
    for path, value in top:
        lines += _value_lines(path, value)
    for node in wf["nodes"]:
        lines += ["", f"== node: {node.get('name', '')}  [{node.get('type')} v{node.get('typeVersion')}]"]
        flat: list[tuple[str, Any]] = []
        for key in sorted(set(node) - {"name", "type", "typeVersion"}):
            _flatten(node[key], key, flat)
        # Position first (one compact line), then everything else in path order.
        pos = node.get("position")
        if isinstance(pos, list):
            lines.append(f"position: {_fmt(pos)}")
            flat = [kv for kv in flat if not kv[0].startswith("position")]
        for path, value in flat:
            lines += _value_lines(path, value)
    lines += ["", "== edges"]
    lines += [edge_text(e) for e in sorted(_edges(wf, {}))]
    return lines


def review_view(workflows: list[dict]) -> str:
    """Node-block text for ``show``/``textconv``: one line per parameter, multi-line strings kept as lines."""
    blocks = ["\n".join(_review_one(w)) for w in workflows]
    return "\n\n".join(blocks) + "\n"
