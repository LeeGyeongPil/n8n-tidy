from conftest import load_fixture
from n8n_tidy import Change, semantic_diff
from n8n_tidy.render import pin_data_warnings


def test_probe_scenario():
    a, b = load_fixture("export-v1.json"), load_fixture("export-v2.json")
    changes = semantic_diff(a, b)
    kinds = [c.kind for c in changes]
    assert set(kinds) == {"layout", "rename", "text"}
    assert kinds.count("layout") == 1 and kinds.count("rename") == 1 and kinds.count("text") == 1
    assert not [c for c in changes if c.kind == "edge"]  # the rename must not scatter into connection changes
    rename = next(c for c in changes if c.kind == "rename")
    assert (rename.before, rename.after) == ("Normalize Ticket", "Prepare Ticket")
    text = next(c for c in changes if c.kind == "text")
    assert text.node == "Triage Agent" and text.path == "parameters.options.systemMessage"
    added = [ln for ln in text.text_diff.splitlines() if ln.startswith("+")]
    assert added == ["+Always answer in Korean."]
    assert pin_data_warnings([a], [b]) == [w for w in pin_data_warnings([a], [b]) if "pinData present in B" in w]
    assert len(pin_data_warnings([a], [b])) == 1


def test_reimport_no_changes():
    assert semantic_diff(load_fixture("export-v1.json"), load_fixture("export-v1-reimported.json")) == []


def test_legacy_without_ids():
    changes = semantic_diff(load_fixture("legacy-no-ids-v1.json"), load_fixture("legacy-no-ids-v2.json"))
    by_kind = {}
    for c in changes:
        by_kind.setdefault(c.kind, []).append(c)
    assert [c.node for c in by_kind["added"]] == ["Archive Orders"]
    assert [c.node for c in by_kind["removed"]] == ["Filter Paid"]
    cred = by_kind["credentials"][0]
    assert cred.node == "Fetch Orders" and cred.path == "credentials.httpBasicAuth"
    assert cred.after["name"] == "Shop API (new)"
    param = by_kind["param"][0]
    assert (param.node, param.path) == ("Send Mail", "parameters.subject")
    assert (param.before, param.after) == ("Orders report", "Daily orders report")
    # Matched by (name, type): unchanged nodes produce nothing, no spurious renames.
    assert "rename" not in by_kind
    assert {c.node for c in by_kind["edge"]} >= {"Fetch Orders", "Filter Paid", "Archive Orders"}


def test_node_type_and_disabled_changes():
    a = load_fixture("export-v1.json")
    b = load_fixture("export-v1.json")
    node = next(n for n in b["nodes"] if n["name"] == "Notify Team")
    node["typeVersion"] = 5
    node["disabled"] = True
    kinds = {c.kind for c in semantic_diff(a, b)}
    assert kinds == {"type", "disabled"}


def test_change_is_a_dataclass_with_defaults():
    c = Change("param")
    assert c.node == "" and c.text_diff == ""
