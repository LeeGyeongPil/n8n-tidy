"""Idempotent normalization of n8n workflow exports.

Every rule lives in the tables below so that new n8n versions can be handled by
editing one place. Unknown top-level fields are never removed (safe default).
"""

from __future__ import annotations

import copy
import json
from typing import Any

from .io import NotAWorkflowError, is_workflow

__all__ = ["VOLATILE_KEYS", "EMPTY_ONLY_KEYS", "normalize", "dumps"]

#: Top-level fields that change on every save/import/export but carry no workflow logic.
VOLATILE_KEYS: tuple[str, ...] = (
    "updatedAt",
    "createdAt",
    "versionId",
    "activeVersionId",
    "versionCounter",
    "triggerCount",
    "isArchived",
    "shared",
    "versionMetadata",
    "homeProject",
    "parentFolder",
    "parentFolderId",
    "scopes",
    "usedCredentials",
    "sharedWithProjects",
    "activeVersion",
    "checksum",
)

#: Fields that newer n8n versions add; dropped only when null/empty so older exports still match.
EMPTY_ONLY_KEYS: tuple[str, ...] = ("description", "nodeGroups", "sourceWorkflowId")

_TAG_VOLATILE = ("createdAt", "updatedAt")


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def normalize(wf: dict, *, keep_pin_data: bool = False, keep_static_data: bool = False) -> dict:
    """Return a normalized deep copy of one workflow.

    Kept on purpose: workflow ``id`` (needed to re-import), node ``position``,
    node ``credentials`` references, and the order of arrays inside ``connections``.
    """
    if not is_workflow(wf):
        raise NotAWorkflowError("normalize() expects one n8n workflow object with 'nodes' and 'connections'.")
    out = copy.deepcopy(wf)

    for key in VOLATILE_KEYS:
        out.pop(key, None)
    for key in EMPTY_ONLY_KEYS:
        if key in out and _is_empty(out[key]):
            del out[key]

    meta = out.get("meta")
    if isinstance(meta, dict):
        meta.pop("instanceId", None)
        if not meta:
            del out["meta"]

    if "pinData" in out and (not keep_pin_data or _is_empty(out["pinData"])):
        del out["pinData"]
    if "staticData" in out and (not keep_static_data or _is_empty(out["staticData"])):
        del out["staticData"]

    tags = out.get("tags")
    if isinstance(tags, list):
        cleaned = []
        for tag in tags:
            if isinstance(tag, dict):
                tag = {k: v for k, v in tag.items() if k not in _TAG_VOLATILE}
            cleaned.append(tag)
        cleaned.sort(key=lambda t: (str(t.get("name", "")), str(t.get("id", ""))) if isinstance(t, dict) else (str(t), ""))
        out["tags"] = cleaned

    nodes = out.get("nodes", [])
    out["nodes"] = sorted(
        nodes,
        key=lambda n: (str(n.get("name", "")), str(n.get("id", ""))) if isinstance(n, dict) else ("", ""),
    )
    return out


def dumps(wf: dict | list) -> str:
    """Canonical text: sorted keys, 2-space indent, UTF-8 characters kept, one trailing newline."""
    return json.dumps(wf, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
