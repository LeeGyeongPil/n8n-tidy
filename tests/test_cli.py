import json

from conftest import FIXTURES, copy_fixture
from n8n_tidy.cli import main

A, B = str(FIXTURES / "export-v1.json"), str(FIXTURES / "export-v2.json")


def test_normalize_dir_in_place_and_check(tmp_path, capsys):
    copy_fixture("export-v1.json", tmp_path / "one.json")
    copy_fixture("export-v1-reimported.json", tmp_path / "two.json")
    copy_fixture("export-array.json", tmp_path / "all.json")
    other = copy_fixture("not-a-workflow.json", tmp_path / "package.json")
    before_other = other.read_bytes()

    assert main(["normalize", "--check", str(tmp_path)]) == 1  # needs normalizing
    assert "needs normalizing" in capsys.readouterr().out
    assert (tmp_path / "one.json").read_text(encoding="utf-8").count("versionId") == 1  # --check changed nothing

    assert main(["normalize", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "skipped" in out and "package.json" in out
    assert other.read_bytes() == before_other

    assert main(["normalize", "--check", str(tmp_path)]) == 0
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()
    assert isinstance(json.loads((tmp_path / "all.json").read_text(encoding="utf-8")), list)


def test_normalize_stdout(capsys):
    assert main(["normalize", "--stdout", A]) == 0
    out = capsys.readouterr().out
    assert "versionId" not in out and json.loads(out)["id"] == "tidyDemo01"


def test_diff_formats(capsys):
    assert main(["diff", A, B, "--format", "md"]) == 0
    md = capsys.readouterr().out
    assert "### Triage Agent" in md and "```diff" in md and "+Always answer in Korean." in md
    assert "### Connections" not in md and "pinData present" in md

    assert main(["diff", A, B, "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {c["kind"] for c in payload["changes"]} == {"layout", "rename", "text"}
    assert payload["warnings"]

    assert main(["diff", A, B, "--no-layout"]) == 0
    assert "(layout only)" not in capsys.readouterr().out


def test_diff_exit_code(capsys):
    assert main(["diff", A, B]) == 0
    capsys.readouterr()
    assert main(["diff", A, B, "--exit-code"]) == 1
    capsys.readouterr()
    assert main(["diff", A, str(FIXTURES / "export-v1-reimported.json"), "--exit-code"]) == 0
    assert "No semantic changes" in capsys.readouterr().out


def test_show_review_view(capsys):
    assert main(["show", B]) == 0
    out = capsys.readouterr().out
    assert "== node: Triage Agent  [@n8n/n8n-nodes-langchain.agent v3.1]" in out
    assert "parameters.options.systemMessage: |\n  You classify incoming support tickets.\n  Always answer in Korean." in out
    assert "Chat Model -[ai_languageModel#0]-> Triage Agent#0" in out
    assert "versionId" not in out and "someone@example.com" not in out
    capsys.readouterr()
    assert main(["textconv", str(FIXTURES / "not-a-workflow.json")]) == 0  # never fails; echoes raw file
    assert "example-package" in capsys.readouterr().out


def test_array_diff_pairs_by_workflow_id(tmp_path, capsys):
    wfs = json.loads((FIXTURES / "export-array.json").read_text(encoding="utf-8"))
    wfs[1]["nodes"][1]["parameters"]["url"] = "https://example.com/changed"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(wfs), encoding="utf-8")
    assert main(["diff", str(FIXTURES / "export-array.json"), str(changed)]) == 0
    out = capsys.readouterr().out
    assert "[Status check B]" in out and "Status check A" not in out


def test_errors_are_friendly(tmp_path, capsys):
    assert main(["diff", A]) == 2
    assert "give two files" in capsys.readouterr().err
    assert main(["diff", A, str(tmp_path / "missing.json")]) == 2
    assert "file not found" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert main(["diff", A, str(bad)]) == 2
    assert "not valid JSON" in capsys.readouterr().err
    assert main(["diff", A, str(FIXTURES / "not-a-workflow.json")]) == 2
    assert "not an n8n workflow" in capsys.readouterr().err


def test_start_command_example(capsys):
    root = FIXTURES.parent.parent
    assert main(["diff", str(root / "examples" / "export-before.json"), str(root / "examples" / "export-after.json")]) == 0
    out = capsys.readouterr().out
    for needle in ("(layout only)", "node renamed:", "+Always answer in Korean.", "pinData present"):
        assert needle in out
    assert "edge" not in out


def test_normalize_skips_non_utf8_like_check(tmp_path, capsys):
    (tmp_path / "bin.json").write_bytes(b"\xff\xfe")
    copy_fixture("export-v1.json", tmp_path / "one.json")
    assert main(["normalize", "--check", str(tmp_path)]) == 1  # only one.json needs normalizing
    out = capsys.readouterr().out
    assert "skipped" in out and "not UTF-8" in out
    assert (tmp_path / "bin.json").read_bytes() == b"\xff\xfe"


# --- check --keep-static-data (staticData kept by normalize must pass check) ---

def _static_file(tmp_path, static):
    data = json.loads((FIXTURES / "export-v1.json").read_text(encoding="utf-8"))
    data["staticData"] = static
    path = tmp_path / "s.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_check_keep_static_data_passes_after_normalize_keep(tmp_path, capsys):
    path = _static_file(tmp_path, {"node:Ticket Webhook": {"lastId": 5}})
    assert main(["normalize", "--keep-static-data", str(path)]) == 0
    capsys.readouterr()
    assert main(["check", "--keep-static-data", str(path)]) == 0
    assert "ok: no problems found." in capsys.readouterr().out
    assert "staticData" in path.read_text(encoding="utf-8")  # positive: value kept


def test_check_without_flag_still_reports_static_data(tmp_path, capsys):
    path = _static_file(tmp_path, {"node:Ticket Webhook": {"lastId": 5}})
    main(["normalize", "--keep-static-data", str(path)])
    capsys.readouterr()
    assert main(["check", str(path)]) == 1  # unchanged behaviour
    out = capsys.readouterr().out
    assert out.count("not-normalized") == 1 and "1 problem(s) found." in out


def test_check_plain_file_passes_with_and_without_flag(tmp_path, capsys):
    path = tmp_path / "p.json"
    copy_fixture("export-v1.json", path)
    main(["normalize", str(path)])
    capsys.readouterr()
    assert main(["check", str(path)]) == 0
    assert main(["check", "--keep-static-data", str(path)]) == 0


def test_check_keep_static_data_empty_static_data_still_flagged(tmp_path, capsys):
    path = _static_file(tmp_path, {})
    assert main(["check", "--keep-static-data", str(path), "--allow", "pin-data"]) == 1
    assert "not-normalized" in capsys.readouterr().out
