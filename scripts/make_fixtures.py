"""Regenerate the hand-written mock fixtures under tests/fixtures and examples/.

The fixtures are *practice mocks*: the envelope (top-level fields, volatile
fields, `shared`, `meta.instanceId`, `versionMetadata`) mirrors what
`n8n export:workflow --backup` writes, while node contents are written from
scratch. All ids, names and addresses are obviously fake.

Run:  python scripts/make_fixtures.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
EXAMPLES = ROOT / "examples"

SYSTEM_PROMPT_V1 = (
    "You classify incoming support tickets.\n"
    "Return one label: billing, bug, or question.\n"
    "Keep the answer under 20 words."
)
SYSTEM_PROMPT_V2 = (
    "You classify incoming support tickets.\n"
    "Always answer in Korean.\n"
    "Return one label: billing, bug, or question.\n"
    "Keep the answer under 20 words."
)


def envelope(wf_id: str, name: str, nodes: list, connections: dict, *, stamp: str, version: str, counter: int) -> dict:
    """Wrap nodes in the export envelope n8n writes with --backup."""
    return {
        "updatedAt": stamp,
        "createdAt": "2026-01-05T09:00:00.000Z",
        "id": wf_id,
        "name": name,
        "description": None,
        "active": False,
        "isArchived": False,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
        "meta": {"instanceId": "0000000000000000000000000000000000000000000000000000000000fake01"},
        "nodeGroups": [],
        "pinData": {},
        "versionId": version,
        "activeVersionId": None,
        "versionCounter": counter,
        "triggerCount": 0,
        "sourceWorkflowId": None,
        "tags": [],
        "shared": [
            {
                "updatedAt": "2026-01-05T09:00:00.100Z",
                "createdAt": "2026-01-05T09:00:00.100Z",
                "role": "workflow:owner",
                "workflowId": wf_id,
                "projectId": "FakeProject000001",
                "project": {
                    "updatedAt": "2026-01-01T00:00:00.000Z",
                    "createdAt": "2026-01-01T00:00:00.000Z",
                    "id": "FakeProject000001",
                    "name": "Unnamed Project",
                    "type": "personal",
                    "icon": None,
                    "description": None,
                    "customTelemetryTags": [],
                    "creatorId": "00000000-0000-4000-8000-000000000001",
                },
            }
        ],
        "versionMetadata": {"name": None, "description": None},
    }


def triage_nodes(prompt: str, first_name: str, trigger_x: int) -> tuple[list, dict]:
    nodes = [
        {
            "parameters": {"path": "tickets", "httpMethod": "POST", "options": {}},
            "id": "tidy-0001-webhook",
            "name": "Ticket Webhook",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [trigger_x, 0],
            "webhookId": "00000000-0000-4000-8000-0000000000aa",
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {"id": "a1", "name": "body", "value": "={{ $json.body.text }}", "type": "string"}
                    ]
                },
                "options": {},
            },
            "id": "tidy-0002-set",
            "name": first_name,
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [220, 0],
        },
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $json.body }}",
                "options": {"systemMessage": prompt},
            },
            "id": "tidy-0003-agent",
            "name": "Triage Agent",
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 3.1,
            "position": [440, 0],
        },
        {
            "parameters": {"model": {"__rl": True, "mode": "list", "value": "example-model"}, "options": {}},
            "id": "tidy-0004-model",
            "name": "Chat Model",
            "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
            "typeVersion": 1.2,
            "position": [400, 220],
            "credentials": {"openAiApi": {"id": "cred-fake-01", "name": "Example OpenAI account"}},
        },
        {
            "parameters": {
                "name": "priority_lookup",
                "description": "Look up the priority of a customer plan.",
                "jsCode": "const plan = query.toLowerCase();\nreturn plan === 'pro' ? 'high' : 'normal';",
            },
            "id": "tidy-0005-tool",
            "name": "Priority Lookup",
            "type": "@n8n/n8n-nodes-langchain.toolCode",
            "typeVersion": 1.3,
            "position": [560, 220],
        },
        {
            "parameters": {
                "conditions": {
                    "conditions": [
                        {
                            "id": "c1",
                            "leftValue": "={{ $json.output }}",
                            "rightValue": "bug",
                            "operator": {"type": "string", "operation": "equals"},
                        }
                    ]
                }
            },
            "id": "tidy-0006-if",
            "name": "Is Bug",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [800, 0],
        },
        {
            "parameters": {"method": "POST", "url": "https://example.com/hooks/bugs", "sendBody": True},
            "id": "tidy-0007-http",
            "name": "Notify Team",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1020, -80],
        },
    ]

    def link(node: str, kind: str = "main") -> dict:
        return {"node": node, "type": kind, "index": 0}

    connections = {
        "Ticket Webhook": {"main": [[link(first_name)]]},
        first_name: {"main": [[link("Triage Agent")]]},
        "Triage Agent": {"main": [[link("Is Bug")]]},
        "Chat Model": {"ai_languageModel": [[link("Triage Agent", "ai_languageModel")]]},
        "Priority Lookup": {"ai_tool": [[link("Triage Agent", "ai_tool")]]},
        "Is Bug": {"main": [[link("Notify Team")], []]},
    }
    return nodes, connections


def build_v1() -> dict:
    nodes, conns = triage_nodes(SYSTEM_PROMPT_V1, "Normalize Ticket", 0)
    return envelope("tidyDemo01", "Ticket triage", nodes, conns,
                    stamp="2026-01-05T09:00:01.000Z", version="11111111-1111-4111-8111-111111111111", counter=1)


def build_reimported() -> dict:
    """Same content, re-imported: only versionId, versionCounter and updatedAt differ."""
    wf = build_v1()
    wf["versionId"] = "22222222-2222-4222-8222-222222222222"
    wf["versionCounter"] = 2
    wf["updatedAt"] = "2026-01-06T10:30:00.000Z"
    return wf


def build_v2() -> dict:
    """A real edit: one prompt line added, trigger moved 40px, one node renamed, pinned data added."""
    nodes, conns = triage_nodes(SYSTEM_PROMPT_V2, "Prepare Ticket", 40)
    wf = envelope("tidyDemo01", "Ticket triage", nodes, conns,
                  stamp="2026-01-07T11:00:00.000Z", version="33333333-3333-4333-8333-333333333333", counter=3)
    wf["pinData"] = {"Ticket Webhook": [{"json": {"body": {"text": "Refund please", "from": "someone@example.com"}}}]}
    return wf


def small_workflow(wf_id: str, name: str, url: str) -> dict:
    nodes = [
        {
            "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 6}]}},
            "id": f"{wf_id}-trigger",
            "name": "Every 6 Hours",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 0],
        },
        {
            "parameters": {"url": url, "options": {}},
            "id": f"{wf_id}-http",
            "name": "Fetch Status",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [240, 0],
        },
    ]
    conns = {"Every 6 Hours": {"main": [[{"node": "Fetch Status", "type": "main", "index": 0}]]}}
    return envelope(wf_id, name, nodes, conns,
                    stamp="2026-02-01T08:00:00.000Z", version=f"44444444-4444-4444-8444-{wf_id[-1] * 12}", counter=1)


def build_array() -> list:
    return [
        small_workflow("tidyArr0001", "Status check A", "https://example.com/status/a"),
        small_workflow("tidyArr0002", "Status check B", "https://example.com/status/b"),
    ]


def legacy(version: int) -> dict:
    """Old export without node ids: nodes can only be matched by (name, type)."""
    trigger = {"parameters": {}, "name": "Daily", "type": "n8n-nodes-base.cron", "typeVersion": 1, "position": [0, 0]}
    fetch = {
        "parameters": {"url": "https://example.com/orders", "method": "GET"},
        "name": "Fetch Orders",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 3,
        "position": [220, 0],
        "credentials": {"httpBasicAuth": {"id": "1", "name": "Shop API"}},
    }
    mail = {
        "parameters": {"subject": "Orders report", "toEmail": "team@example.com"},
        "name": "Send Mail",
        "type": "n8n-nodes-base.emailSend",
        "typeVersion": 2,
        "position": [660, 0],
    }
    if version == 1:
        flt = {"parameters": {"conditions": {}}, "name": "Filter Paid", "type": "n8n-nodes-base.if",
               "typeVersion": 1, "position": [440, 0]}
        nodes = [trigger, fetch, flt, mail]
        conns = {
            "Daily": {"main": [[{"node": "Fetch Orders", "type": "main", "index": 0}]]},
            "Fetch Orders": {"main": [[{"node": "Filter Paid", "type": "main", "index": 0}]]},
            "Filter Paid": {"main": [[{"node": "Send Mail", "type": "main", "index": 0}]]},
        }
    else:
        fetch = copy.deepcopy(fetch)
        fetch["credentials"] = {"httpBasicAuth": {"id": "2", "name": "Shop API (new)"}}
        mail = copy.deepcopy(mail)
        mail["parameters"]["subject"] = "Daily orders report"
        archive = {"parameters": {"values": {}}, "name": "Archive Orders", "type": "n8n-nodes-base.set",
                   "typeVersion": 1, "position": [440, 0]}
        nodes = [trigger, fetch, archive, mail]
        conns = {
            "Daily": {"main": [[{"node": "Fetch Orders", "type": "main", "index": 0}]]},
            "Fetch Orders": {"main": [[{"node": "Archive Orders", "type": "main", "index": 0}]]},
            "Archive Orders": {"main": [[{"node": "Send Mail", "type": "main", "index": 0}]]},
        }
    return {
        "name": "Orders report",
        "nodes": nodes,
        "connections": conns,
        "active": False,
        "settings": {},
        "versionId": f"legacy-version-{version}",
    }


def write(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    write(FIXTURES / "export-v1.json", build_v1())
    write(FIXTURES / "export-v1-reimported.json", build_reimported())
    write(FIXTURES / "export-v2.json", build_v2())
    write(FIXTURES / "export-array.json", build_array())
    write(FIXTURES / "legacy-no-ids-v1.json", legacy(1))
    write(FIXTURES / "legacy-no-ids-v2.json", legacy(2))
    write(FIXTURES / "not-a-workflow.json",
          {"name": "example-package", "version": "1.0.0", "scripts": {"test": "echo ok"}})
    write(EXAMPLES / "export-before.json", build_v1())
    write(EXAMPLES / "export-after.json", build_v2())


if __name__ == "__main__":
    main()
