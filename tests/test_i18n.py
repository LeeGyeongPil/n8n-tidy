"""Language selection and the en/ko message tables."""

import re
import string

import pytest

from conftest import FIXTURES, copy_fixture
from n8n_tidy import gitio, i18n
from n8n_tidy.cli import build_parser, main
from n8n_tidy.io import TidyError, load, parse

A, B = str(FIXTURES / "export-v1.json"), str(FIXTURES / "export-v2.json")
HANGUL = re.compile(r"[가-힣]")
# A fixed particle right after a placeholder reads wrong for some values ("{path} 를" vs "{path} 을").
FIXED_PARTICLE = re.compile(r"\}\s*(이\(가\)|은\(는\)|을\(를\)|가|이|은|는|을|를|에서|으로|로|와|과)(?=[\s.,:)]|$)")


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


# --- tables ---

def test_tables_have_identical_keys_and_placeholders():
    assert set(i18n.EN) == set(i18n.KO)
    for key in i18n.EN:
        assert _fields(i18n.EN[key]) == _fields(i18n.KO[key]), key


def test_korean_values_are_korean_and_particle_free():
    for key, value in i18n.KO.items():
        assert HANGUL.search(value), key
        assert not FIXED_PARTICLE.search(value), f"{key}: {value}"


def test_particle_regex_catches_bad_phrases():
    assert FIXED_PARTICLE.search("{path} 를 읽습니다")
    assert FIXED_PARTICLE.search("{path}을(를) 읽습니다")
    assert not FIXED_PARTICLE.search("파일: {path}")


def test_every_error_code_raised_by_the_library_has_a_message():
    for code in ("invalid_json", "not_workflow", "file_not_found", "cannot_read", "path_not_found", "git_missing",
                 "git_timeout", "git_failed", "bad_rev", "cannot_read_rev", "not_git_repo", "bad_pattern",
                 "empty_command"):
        assert f"e.{code}" in i18n.EN


# --- resolution order ---

def test_resolve_priority():
    env = {"N8N_TIDY_LANG": "en", "LANG": "ko_KR.UTF-8"}
    assert i18n.resolve_lang("ko", env) == "ko"  # --lang beats everything
    assert i18n.resolve_lang(None, env) == "en"  # N8N_TIDY_LANG beats LANG
    assert i18n.resolve_lang(None, {"LANG": "ko_KR.UTF-8"}) == "ko"
    assert i18n.resolve_lang(None, {"LANG": "fr_FR.UTF-8"}) == "en"
    assert i18n.resolve_lang(None, {"LC_ALL": "en_US.UTF-8", "LANG": "ko_KR.UTF-8"}) == "en"
    assert i18n.resolve_lang(None, {"LC_MESSAGES": "ko_KR", "LANG": "en_US"}) == "ko"
    assert i18n.resolve_lang(None, {}) == "en"
    assert i18n.resolve_lang("xx", {"LANG": "ko_KR.UTF-8"}) == "ko"  # invalid CLI value is ignored here


def test_cli_lang_option_beats_env_var(monkeypatch, capsys):
    monkeypatch.setenv("N8N_TIDY_LANG", "ko")
    assert main(["--lang", "en", "check", B]) == 1
    assert "problem(s) found" in capsys.readouterr().out
    assert main(["check", "--lang", "ko", B]) == 1  # the option is also accepted after the sub-command
    out = capsys.readouterr().out
    assert "문제" in out and "problem(s)" not in out


def test_env_var_and_lang_variable(monkeypatch, capsys):
    monkeypatch.delenv("N8N_TIDY_LANG")
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    main(["check", A])
    assert HANGUL.search(capsys.readouterr().out)
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    main(["check", A])
    out = capsys.readouterr().out
    assert not HANGUL.search(out)


# --- invalid --lang ---

def test_invalid_lang_reports_once_with_exit_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--lang", "fr", "check", A])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert err.count("invalid choice") == 1
    assert err.count("error:") == 1


def test_invalid_lang_after_subcommand_reports_once(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["check", A, "--lang=fr"])
    assert exc.value.code == 2
    assert capsys.readouterr().err.count("error:") == 1


def test_missing_lang_value_reports_once(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["check", A, "--lang"])
    assert exc.value.code == 2
    assert capsys.readouterr().err.count("error:") == 1


# --- Korean output ---

def test_ko_check_output(capsys):
    assert main(["--lang", "ko", "check", B]) == 1
    out = capsys.readouterr().out
    assert "problem(s) found" not in out and "no problems" not in out
    assert re.search(r"문제 \d+건을 찾았습니다\.", out)


def test_ko_check_ok_and_problems(tmp_path, capsys):
    clean = copy_fixture("export-v1.json", tmp_path / "w.json")
    assert main(["normalize", str(clean)]) == 0
    capsys.readouterr()
    assert main(["--lang", "ko", "check", str(clean)]) == 0
    assert capsys.readouterr().out.strip() == "이상 없음: 문제를 찾지 못했습니다."
    dirty = copy_fixture("export-v1.json", tmp_path / "d.json")
    assert main(["--lang", "ko", "check", str(dirty)]) == 1
    out = capsys.readouterr().out
    assert re.search(r"^문제 \d+건을 찾았습니다\.$", out, re.M)
    assert "problem(s)" not in out


def test_ko_normalize_messages(tmp_path, capsys):
    f = copy_fixture("export-v1.json", tmp_path / "w.json")
    other = copy_fixture("not-a-workflow.json", tmp_path / "package.json")
    assert main(["--lang", "ko", "normalize", "--check", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert f"정규화 필요: {f}" in out
    assert f"건너뜀: {other} (n8n 워크플로가 아님)" in out
    assert main(["--lang", "ko", "normalize", str(tmp_path)]) == 0
    assert f"정규화 완료: {f}" in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    main(["--lang", "ko", "normalize", str(bad)])
    assert f"건너뜀: {bad} (올바르지 않은 JSON)" in capsys.readouterr().out
    binary = tmp_path / "bin.json"
    binary.write_bytes(b"\xff\xfe\x00")
    main(["--lang", "ko", "normalize", str(binary)])
    assert f"건너뜀: {binary} (UTF-8 텍스트가 아님)" in capsys.readouterr().out


def test_ko_error_messages_from_library_exceptions(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    assert main(["--lang", "ko", "normalize", str(missing)]) == 2
    assert capsys.readouterr().err == f"n8n-tidy: 오류: {missing}: 경로를 찾을 수 없습니다.\n"
    assert main(["--lang", "ko", "diff", str(missing), B]) == 2
    assert "파일을 찾을 수 없습니다" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert main(["--lang", "ko", "diff", str(bad), B]) == 2
    err = capsys.readouterr().err
    assert "올바른 JSON 이 아닙니다" in err and "not valid JSON" not in err
    assert main(["--lang", "ko", "diff", str(FIXTURES / "not-a-workflow.json"), B]) == 2
    assert "워크플로 내보내기 파일이 아닙니다" in capsys.readouterr().err
    assert main(["--lang", "ko", "diff", "--rev=-x", B]) == 2
    assert "잘못된 리비전" in capsys.readouterr().err


def test_ko_cli_usage_errors(capsys):
    assert main(["--lang", "ko", "normalize", "--stdout", A, B]) == 2
    assert capsys.readouterr().err == "n8n-tidy: 오류: --stdout 은 파일을 정확히 하나만 받습니다.\n"
    assert main(["--lang", "ko", "diff", A]) == 2
    assert "파일 두 개" in capsys.readouterr().err
    assert main(["--lang", "ko", "diff", "--rev", "HEAD", A, B]) == 2
    assert "--rev" in capsys.readouterr().err


def test_en_errors_unchanged(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    assert main(["normalize", str(missing)]) == 2
    assert capsys.readouterr().err == f"n8n-tidy: error: {missing}: path not found.\n"


def test_ko_git_errors_and_install(isolated_git, tmp_path, capsys):
    repo, _ = isolated_git
    assert main(["--lang", "ko", "uninstall-git"]) == 0
    assert capsys.readouterr().out.strip() == "제거할 항목이 없습니다."
    assert main(["--lang", "ko", "install-git", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("(미리 보기) .gitattributes: *.json diff=n8n")
    assert main(["--lang", "ko", "install-git", "--pattern", ""]) == 2
    assert "--pattern 은" in capsys.readouterr().err
    assert main(["--lang", "ko", "install-git", "--command", " "]) == 2
    assert "--command 는" in capsys.readouterr().err


def test_ko_not_in_git_repo(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert main(["--lang", "ko", "install-git"]) == 2
    assert "git 저장소 안이 아닙니다" in capsys.readouterr().err


def test_ko_help_is_korean(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--lang", "ko", "check", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "해당 종류를 무시합니다" in out
    assert "ignore a kind" not in out
    with pytest.raises(SystemExit):
        main(["--lang", "ko", "--help"])
    out = capsys.readouterr().out
    assert "정규화하고, 비교하고, 점검합니다" in out and "rewrite exports" not in out
    assert "pinData, 정규화되지 않은 파일" in out and "find pinData" not in out


def test_help_defaults_to_english(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "Normalize, diff and check" in capsys.readouterr().out


def test_build_parser_default_language_is_english():
    assert "Normalize, diff" in build_parser().format_help()
    assert "정규화" in build_parser("ko").format_help()


# --- things that must not change ---

def test_json_diff_is_identical_in_both_languages(capsysbinary):
    assert main(["--lang", "en", "diff", "--format", "json", A, B]) == 0
    en = capsysbinary.readouterr().out
    assert main(["--lang", "ko", "diff", "--format", "json", A, B]) == 0
    ko = capsysbinary.readouterr().out
    assert en == ko and en


def test_text_diff_and_show_are_not_translated(capsys):
    main(["--lang", "en", "diff", A, B])
    en = capsys.readouterr().out
    main(["--lang", "ko", "diff", A, B])
    assert capsys.readouterr().out == en
    main(["--lang", "en", "show", A])
    en = capsys.readouterr().out
    main(["--lang", "ko", "show", A])
    assert capsys.readouterr().out == en


def test_library_error_text_and_codes():
    with pytest.raises(TidyError) as exc:
        load("/nonexistent/x.json")
    assert str(exc.value) == "/nonexistent/x.json: file not found."
    assert exc.value.code == "file_not_found" and exc.value.params == {"path": "/nonexistent/x.json"}
    assert TidyError("plain").code is None and TidyError("plain").params == {}
    with pytest.raises(ValueError, match="not valid JSON"):
        parse("{", "src")
    with pytest.raises(gitio.GitError, match="must not start with"):
        gitio.show_revision("-x", "a.json")
