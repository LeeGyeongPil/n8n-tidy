import pytest

from conftest import FIXTURES, copy_fixture
from n8n_tidy.cli import main
from n8n_tidy.check import check_text, mask


def fake_token() -> str:
    # Assembled at run time so no token-shaped string is ever committed.
    # "".join over a list is a runtime call, so the .pyc holds no folded token constant.
    return "".join(["sk", "-", "Abcdefghij0123456789", "KLMNOP"])


def test_v2_reports_three_kinds(capsys):
    code = main(["check", str(FIXTURES / "export-v2.json")])
    out = capsys.readouterr().out
    assert code == 1
    for kind in ("pin-data", "not-normalized", "instance-info"):
        assert kind in out
    assert "export-v2.json: Ticket Webhook > pinData.Ticket Webhook: pin-data" in out
    assert "secret-suspect" not in out


def test_clean_normalized_file_passes(tmp_path, capsys):
    target = tmp_path / "wf.json"
    copy_fixture("export-v1.json", target)
    assert main(["normalize", str(target)]) == 0
    capsys.readouterr()
    assert main(["check", str(target)]) == 0
    assert "ok" in capsys.readouterr().out


def test_secret_suspect_is_masked(tmp_path, capsys):
    import json
    from n8n_tidy import dumps, normalize

    wf = json.loads((FIXTURES / "export-v1.json").read_text(encoding="utf-8"))
    http = next(n for n in wf["nodes"] if n["name"] == "Notify Team")
    http["parameters"]["headerParameters"] = {"parameters": [{"name": "Authorization", "value": "Bearer " + fake_token()}]}
    http["parameters"]["url"] = "={{ 'Bearer ' + $env.TOKEN_FAKE_VALUE_PLACEHOLDER }}"  # expression: ignored
    target = tmp_path / "token.json"
    target.write_text(dumps(normalize(wf)), encoding="utf-8")
    code = main(["check", str(target)])
    out = capsys.readouterr().out
    assert code == 1
    assert "token.json: Notify Team > parameters.headerParameters.parameters[0].value: secret-suspect" in out
    assert fake_token() not in out and fake_token()[:12] not in out
    assert "sk-A****" in out
    assert "url" not in out


def test_allow_option(tmp_path):
    target = copy_fixture("export-v2.json", tmp_path / "v2.json")
    code = main(["check", str(target), "--allow", "pin-data", "--allow", "not-normalized", "--allow", "instance-info"])
    assert code == 0


def test_skips_non_workflow(tmp_path, capsys):
    copy_fixture("not-a-workflow.json", tmp_path / "package.json")
    assert main(["check", str(tmp_path)]) == 0
    assert "skipped" in capsys.readouterr().out


def test_mask_and_unknown_kind():
    assert mask("abcdefghijkl") == "abcd****"
    with pytest.raises(ValueError):
        check_text((FIXTURES / "export-v1.json").read_text(encoding="utf-8"), "x", ["nope"])


def _write_with_params(tmp_path, header_value, json_body):
    import json
    from n8n_tidy import dumps, normalize

    wf = json.loads((FIXTURES / "export-v1.json").read_text(encoding="utf-8"))
    http = next(n for n in wf["nodes"] if n["name"] == "Notify Team")
    http["parameters"]["headerParameters"] = {"parameters": [{"name": "Authorization", "value": header_value}]}
    http["parameters"]["jsonBody"] = json_body
    target = tmp_path / "expr.json"
    target.write_text(dumps(normalize(wf)), encoding="utf-8")
    return target


def test_token_literal_inside_expression_is_reported(tmp_path, capsys):
    token = fake_token()
    target = _write_with_params(
        tmp_path,
        "=Bearer " + token + " {{ $json.id }}",
        '={"key": "' + token + '", "id": "{{ $json.id }}"}',
    )
    code = main(["check", str(target)])
    out = capsys.readouterr().out
    assert code == 1
    assert "Notify Team > parameters.headerParameters.parameters[0].value: secret-suspect" in out
    assert "Notify Team > parameters.jsonBody: secret-suspect" in out
    assert token not in out and token[:12] not in out


@pytest.mark.parametrize(
    "value, reported",
    [
        ("={{ $env.TOKEN }}", False),
        ('={"id": "{{ $json.id }}"}', False),
        ("={{ 'Bearer ' + $env.TOKEN_FAKE_VALUE_PLACEHOLDER }}", False),
        ("=Bearer {{ $env.TOKEN_FAKE_VALUE_PLACEHOLDER }}", False),
        ("={{ '" + fake_token() + "' }}", False),  # token only inside {{ }}: unchanged behaviour
        ("=prefix " + fake_token(), True),
        ("={{ $json.a }} " + fake_token() + " {{ $json.b }}", True),
        ("={{ $json.a " + fake_token(), True),  # unclosed '{{': checked as-is (conservative)
        ("plain " + fake_token(), True),
        ("plain text with no secret", False),
    ],
)
def test_expression_token_table(tmp_path, capsys, value, reported):
    target = _write_with_params(tmp_path, value, "plain")
    code = main(["check", str(target)])
    out = capsys.readouterr().out
    assert (code == 1) is reported
    assert ("secret-suspect" in out) is reported
    assert fake_token() not in out


def _join(*parts: str) -> str:
    # Runtime call: the interpreter cannot constant-fold it, so no token-shaped
    # string lands in the compiled .pyc either.
    return "".join(parts)


def _other_tokens() -> dict[str, str]:
    return {
        "bearer_plain": _join("Bearer ", "abcdefghijklmnop", "qrstuvwxyz012345"),
        "gh": _join("gh", "p_", "A1b2C3d4E5f6G7h8", "I9j0K1l2M3n4O5p6Q7r8"),
        "xox": _join("xox", "b-", "1234567890", "-abcdefghij"),
        "aws": _join("AK", "IA", "ABCDEFGH", "IJKLMNOP"),
    }


def _secret_problems(tmp_path, value):
    target = _write_with_params(tmp_path, value, "plain")
    return [p for p in check_text(target.read_text(encoding="utf-8"), "t.json") if p.kind == "secret-suspect"]


def test_bearer_with_sk_token_is_reported_once(tmp_path, capsys):
    # Regression: the sk- pattern and the Bearer pattern used to both report the same token.
    target = _write_with_params(tmp_path, "Bearer " + fake_token(), "plain")
    code = main(["check", str(target)])
    out = capsys.readouterr().out
    assert code == 1
    lines = [l for l in out.splitlines() if "secret-suspect" in l]
    assert len(lines) == 1
    assert out.strip().splitlines()[-1].startswith("1 problem")
    assert fake_token() not in out


@pytest.mark.parametrize("prefix", ["Bearer ", "Bearer  ", "=Bearer "])
def test_bearer_prefixed_token_counts_once(tmp_path, prefix):
    assert len(_secret_problems(tmp_path, prefix + fake_token())) == 1


@pytest.mark.parametrize("name", ["bearer_plain", "gh", "xox", "aws"])
def test_other_tokens_still_detected_once(tmp_path, name):
    token = _other_tokens()[name]
    probs = _secret_problems(tmp_path, token)
    assert len(probs) == 1
    assert token not in probs[0].format()
    assert probs[0].detail.endswith(mask(token.split()[-1]))


def test_bearer_with_gh_token_is_reported_once(tmp_path):
    assert len(_secret_problems(tmp_path, "Bearer " + _other_tokens()["gh"])) == 1


def test_bare_sk_token_still_detected_once(tmp_path):
    assert len(_secret_problems(tmp_path, fake_token())) == 1


def test_distinct_tokens_in_one_value_are_each_reported(tmp_path):
    toks = _other_tokens()
    assert len(_secret_problems(tmp_path, fake_token() + " " + toks["gh"])) == 2
    assert len(_secret_problems(tmp_path, "Bearer " + fake_token() + " " + toks["aws"])) == 2


def test_check_text_keep_static_data():
    import json as _json
    from n8n_tidy.normalize import dumps, normalize

    wf = _json.loads((FIXTURES / "export-v1.json").read_text(encoding="utf-8"))
    wf["staticData"] = {"node:Ticket Webhook": {"lastId": 5}}
    text = dumps(normalize(wf, keep_static_data=True))
    assert check_text(text, "s.json", keep_static_data=True) == []
    assert [p.kind for p in check_text(text, "s.json")] == ["not-normalized"]
