import json

from conftest import load_fixture
from n8n_tidy import dumps, normalize
from n8n_tidy.normalize import VOLATILE_KEYS


def test_volatile_fields_removed():
    raw = load_fixture("export-v2.json")
    out = normalize(raw)
    for key in VOLATILE_KEYS + ("pinData", "staticData", "description", "nodeGroups", "sourceWorkflowId"):
        assert key not in out, key
    assert "meta" not in out  # instanceId was its only key
    # Kept on purpose: workflow id, node ids, positions, credential references.
    assert out["id"] == "tidyDemo01"
    agent = next(n for n in out["nodes"] if n["name"] == "Triage Agent")
    assert agent["id"] == "tidy-0003-agent" and agent["position"] == [440, 0]
    model = next(n for n in out["nodes"] if n["name"] == "Chat Model")
    assert model["credentials"]["openAiApi"]["id"] == "cred-fake-01"
    assert "someone@example.com" not in dumps(out)
    # The input is never mutated.
    assert "pinData" in raw and "shared" in raw


def test_keep_pin_data_option():
    out = normalize(load_fixture("export-v2.json"), keep_pin_data=True)
    assert "Ticket Webhook" in out["pinData"]


def test_reimport_same_bytes():
    a = dumps(normalize(load_fixture("export-v1.json")))
    b = dumps(normalize(load_fixture("export-v1-reimported.json")))
    assert a == b
    assert a.endswith("}\n") and not a.endswith("\n\n")


def test_idempotent():
    once = normalize(load_fixture("export-v2.json"))
    twice = normalize(once)
    assert once == twice
    assert dumps(once) == dumps(twice)
    assert normalize(json.loads(dumps(once))) == once


def test_array_form_preserved():
    from n8n_tidy.io import parse

    text = (__import__("conftest").FIXTURES / "export-array.json").read_text(encoding="utf-8")
    workflows, is_array = parse(text)
    assert is_array and len(workflows) == 2
    normalized = [normalize(w) for w in workflows]
    assert all("versionId" not in w and "shared" not in w for w in normalized)
    assert [w["id"] for w in normalized] == ["tidyArr0001", "tidyArr0002"]
    assert json.loads(dumps(normalized)) == normalized  # still a JSON array


def test_not_a_workflow_raises():
    import pytest
    from n8n_tidy import NotAWorkflowError

    with pytest.raises(NotAWorkflowError):
        normalize({"name": "package"})
