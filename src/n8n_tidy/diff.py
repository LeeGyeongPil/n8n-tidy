"""Semantic diff between two n8n workflow exports.

Nodes are paired by ``id`` first, then by ``(name, type)`` (old exports have no ids).
Renames are applied to the old connections before comparing them, so renaming a node
shows up as one "node renamed" change instead of many connection changes.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

from .normalize import normalize

__all__ = ["Change", "semantic_diff", "diff_documents", "PROMPT_KEYS", "CODE_KEYS"]

#: Parameter keys whose values are prompts or code: diffed line by line.
PROMPT_KEYS = frozenset({"systemMessage", "text", "prompt", "message", "content"})
CODE_KEYS = frozenset({"jsCode", "pythonCode", "query"})
_LONG_TEXT = 160
_NODE_CORE_KEYS = {"id", "name", "type", "typeVersion", "position", "parameters", "credentials", "disabled"}
_SKIP_TOP = {"nodes", "connections", "pinData"}


@dataclass
class Change:
    """One reportable difference.

    ``kind`` is one of: ``field``, ``added``, ``removed``, ``rename``, ``type``, ``disabled``,
    ``credentials``, ``param``, ``text``, ``layout``, ``edge``, ``workflow``.
    """

    kind: str
    node: str = ""
    path: str = ""
    before: Any = None
    after: Any = None
    text_diff: str = ""
    workflow: str = ""


def _is_text_param(path: str, before: Any, after: Any) -> bool:
    values = [v for v in (before, after) if isinstance(v, str)]
    if not values or any(v is not None and not isinstance(v, str) for v in (before, after)):
        return False
    leaf = path.rsplit(".", 1)[-1].split("[", 1)[0]
    if leaf in PROMPT_KEYS or leaf in CODE_KEYS:
        return True
    return any("\n" in v or len(v) > _LONG_TEXT for v in values)


def _flatten(value: Any, prefix: str, out: dict[str, Any]) -> None:
    if isinstance(value, dict) and value:
        for key in sorted(value):
            _flatten(value[key], f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(value, list) and value:
        for i, item in enumerate(value):
            _flatten(item, f"{prefix}[{i}]", out)
    else:
        out[prefix] = value


def _text_diff(before: Any, after: Any) -> str:
    a = (before or "").split("\n")
    b = (after or "").split("\n")
    lines = list(difflib.unified_diff(a, b, "before", "after", lineterm="", n=2))
    return "\n".join(lines[2:])  # drop the ---/+++ header, keep hunks


def _match_nodes(a_nodes: list[dict], b_nodes: list[dict]) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    pairs: list[tuple[dict, dict]] = []
    b_left = list(b_nodes)
    a_left: list[dict] = []
    b_ids = {n["id"]: n for n in b_nodes if n.get("id")}
    used: set[int] = set()
    for a in a_nodes:
        b = b_ids.get(a.get("id")) if a.get("id") else None
        if b is not None and id(b) not in used:
            used.add(id(b))
            pairs.append((a, b))
        else:
            a_left.append(a)
    b_left = [b for b in b_left if id(b) not in used]
    removed: list[dict] = []
    for a in a_left:  # second pass: same name and type
        hit = next((b for b in b_left if b.get("name") == a.get("name") and b.get("type") == a.get("type")), None)
        if hit is not None:
            b_left.remove(hit)
            pairs.append((a, hit))
        else:
            removed.append(a)
    return pairs, removed, b_left


def _edges(wf: dict, rename: dict[str, str]) -> set[tuple[str, str, int, str, int]]:
    result: set[tuple[str, str, int, str, int]] = set()
    connections = wf.get("connections", {})
    for src, kinds in connections.items():
        if not isinstance(kinds, dict):
            continue
        for ctype, outputs in kinds.items():
            if not isinstance(outputs, list):
                continue
            for out_idx, targets in enumerate(outputs):
                for t in targets or []:
                    if isinstance(t, dict) and "node" in t:
                        dst = rename.get(t["node"], t["node"])
                        result.add((rename.get(src, src), t.get("type", ctype), out_idx, dst, int(t.get("index", 0))))
    return result


def edge_text(edge: tuple[str, str, int, str, int]) -> str:
    src, ctype, out_idx, dst, in_idx = edge
    return f"{src} -[{ctype}#{out_idx}]-> {dst}#{in_idx}"


def semantic_diff(a: dict, b: dict) -> list[Change]:
    """Compare two workflows after normalization (``pinData`` is not compared)."""
    a = normalize(a)
    b = normalize(b)
    changes: list[Change] = []

    for key in sorted((set(a) | set(b)) - _SKIP_TOP):
        if a.get(key) != b.get(key):
            changes.append(Change("field", path=key, before=a.get(key), after=b.get(key)))

    pairs, removed, added = _match_nodes(a["nodes"], b["nodes"])
    rename: dict[str, str] = {}
    for old, new in pairs:
        if old.get("name") != new.get("name"):
            rename[old["name"]] = new["name"]

    for old, new in pairs:
        name = new.get("name", "")
        if old.get("name") != new.get("name"):
            changes.append(Change("rename", name, "name", old.get("name"), new.get("name")))
        if (old.get("type"), old.get("typeVersion")) != (new.get("type"), new.get("typeVersion")):
            changes.append(Change("type", name, "type",
                                  f"{old.get('type')} v{old.get('typeVersion')}",
                                  f"{new.get('type')} v{new.get('typeVersion')}"))
        if old.get("disabled", False) != new.get("disabled", False):
            changes.append(Change("disabled", name, "disabled", old.get("disabled", False), new.get("disabled", False)))

        old_cred, new_cred = old.get("credentials") or {}, new.get("credentials") or {}
        for key in sorted(set(old_cred) | set(new_cred)):
            if old_cred.get(key) != new_cred.get(key):
                changes.append(Change("credentials", name, f"credentials.{key}", old_cred.get(key), new_cred.get(key)))

        flat_old: dict[str, Any] = {}
        flat_new: dict[str, Any] = {}
        _flatten(old.get("parameters", {}), "parameters", flat_old)
        _flatten(new.get("parameters", {}), "parameters", flat_new)
        for path in sorted(set(flat_old) | set(flat_new)):
            before, after = flat_old.get(path), flat_new.get(path)
            if before == after and (path in flat_old) == (path in flat_new):
                continue
            if _is_text_param(path, before, after):
                changes.append(Change("text", name, path, before, after, _text_diff(before, after)))
            else:
                changes.append(Change("param", name, path, before, after))

        for key in sorted((set(old) | set(new)) - _NODE_CORE_KEYS):
            if old.get(key) != new.get(key):
                changes.append(Change("param", name, key, old.get(key), new.get(key)))

        if old.get("position") != new.get("position"):
            changes.append(Change("layout", name, "position", old.get("position"), new.get("position")))

    for node in added:
        changes.append(Change("added", node.get("name", ""), "", None, f"{node.get('type')} v{node.get('typeVersion')}"))
    for node in removed:
        changes.append(Change("removed", node.get("name", ""), "", f"{node.get('type')} v{node.get('typeVersion')}", None))

    edges_a, edges_b = _edges(a, rename), _edges(b, {})
    for edge in sorted(edges_a - edges_b):
        changes.append(Change("edge", edge[0], edge_text(edge), edge_text(edge), None))
    for edge in sorted(edges_b - edges_a):
        changes.append(Change("edge", edge[0], edge_text(edge), None, edge_text(edge)))
    return changes


def diff_documents(a_docs: list[dict], b_docs: list[dict]) -> list[Change]:
    """Diff two files that may each hold several workflows (array exports), pairing by workflow id."""
    changes: list[Change] = []
    b_by_id = {w.get("id"): w for w in b_docs if w.get("id")}
    used: set[int] = set()
    unpaired_a: list[dict] = []
    pairs: list[tuple[dict, dict]] = []
    for w in a_docs:
        hit = b_by_id.get(w.get("id")) if w.get("id") else None
        if hit is not None and id(hit) not in used:
            used.add(id(hit))
            pairs.append((w, hit))
        else:
            unpaired_a.append(w)
    unpaired_b = [w for w in b_docs if id(w) not in used]
    # Documents without a shared id are paired by position (single-workflow files with different ids included).
    while unpaired_a and unpaired_b:
        pairs.append((unpaired_a.pop(0), unpaired_b.pop(0)))
    for old, new in pairs:
        for c in semantic_diff(old, new):
            c.workflow = str(new.get("name", ""))
            changes.append(c)
    for w in unpaired_a:
        changes.append(Change("workflow", path="removed", before=w.get("name"), workflow=str(w.get("name", ""))))
    for w in unpaired_b:
        changes.append(Change("workflow", path="added", after=w.get("name"), workflow=str(w.get("name", ""))))
    return changes
