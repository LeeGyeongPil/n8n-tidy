"""Message tables (English and Korean) and language resolution for the command line.

Only the CLI's own wording is translated. Diff bodies, review views, check problem lines,
git configuration lines and the workflow JSON itself are printed as-is.
"""

from __future__ import annotations

import os
from typing import Mapping

__all__ = ["LANGS", "MESSAGES", "ENV_VAR", "resolve_lang", "t"]

LANGS = ("en", "ko")
ENV_VAR = "N8N_TIDY_LANG"

# Korean strings: polite style, and never a fixed particle right after a {placeholder}.
EN: dict[str, str] = {
    # --- help text ---
    "help.description": "Normalize, diff and check n8n workflow exports for git.",
    "help.lang": "output language for messages: en or ko (default: N8N_TIDY_LANG, then LC_ALL/LC_MESSAGES/LANG)",
    "help.normalize": "rewrite exports into a stable form (files or folders)",
    "help.normalize.stdout": "print the result instead of rewriting (one file)",
    "help.normalize.check": "change nothing; exit 1 if any file needs normalizing",
    "help.normalize.keep_pin_data": "keep pinData (removed by default)",
    "help.normalize.keep_static_data": "keep staticData (removed by default)",
    "help.diff": "semantic diff of two exports, or of REV vs the working tree",
    "help.diff.paths": "two files A B, or one PATH with --rev",
    "help.diff.rev": "compare PATH at git revision REV against the working tree",
    "help.diff.no_layout": "hide node position (layout only) changes",
    "help.diff.exit_code": "exit 1 when there are changes",
    "help.show": "print the node-block review view of an export",
    "help.textconv": "git diff driver entry point (same as show, never fails)",
    "help.check": "find pinData, un-normalized files, instance info, token-like strings",
    "help.check.allow": "ignore a kind (repeatable): {kinds}",
    "help.check.keep_static_data": "expect staticData to be kept (matches `normalize --keep-static-data`)",
    "help.install": "register the diff driver in this repository's local git config",
    "help.install.pattern": "gitattributes pattern (default: *.json)",
    "help.install.command": "how git should call n8n-tidy (default: n8n-tidy)",
    "help.install.dry_run": "print what would be written",
    "help.uninstall": "remove what install-git wrote",
    # --- CLI output ---
    "out.error": "n8n-tidy: error: {msg}",
    "out.skipped_not_workflow": "skipped: {path} (not an n8n workflow)",
    "out.skipped_invalid_json": "skipped: {path} (invalid JSON)",
    "out.skipped_not_utf8": "skipped: {path} (not UTF-8 text)",
    "out.needs_normalizing": "needs normalizing: {path}",
    "out.normalized": "normalized: {path}",
    "out.problems_found": "{count} problem(s) found.",
    "out.ok": "ok: no problems found.",
    "out.nothing_to_remove": "nothing to remove.",
    "out.dry_run": "(dry run)",
    # --- CLI usage errors ---
    "err.stdout_one_file": "--stdout needs exactly one file.",
    "err.rev_one_path": "with --rev give exactly one PATH (REV is compared with the working tree).",
    "err.diff_two_files": "give two files: n8n-tidy diff A B  (or one PATH with --rev REV).",
    # --- library errors (code -> message) ---
    "e.invalid_json": "{source}: not valid JSON ({detail}). Re-export the workflow or fix the file.",
    "e.not_workflow": "{source}: not an n8n workflow export (expected an object or array with 'nodes' and 'connections').",
    "e.file_not_found": "{path}: file not found.",
    "e.cannot_read": "{path}: cannot read as UTF-8 text ({detail}).",
    "e.path_not_found": "{path}: path not found.",
    "e.git_missing": "git was not found on PATH. Install git first.",
    "e.git_timeout": "git {args} timed out after {seconds}s.",
    "e.git_failed": "git {args} failed: {detail}",
    "e.bad_rev": "invalid revision {rev}: must not start with '-'.",
    "e.cannot_read_rev": (
        "cannot read {path} at {rev}: {detail}. Check that the revision exists and the file is tracked there."
    ),
    "e.not_git_repo": "not inside a git repository. Run `git init` first, then re-run install-git.",
    "e.bad_pattern": "--pattern must be a non-empty single-line glob such as 'workflows/**/*.json'.",
    "e.empty_command": "--command must not be empty.",
}

KO: dict[str, str] = {
    "help.description": "git 에서 쓰기 좋게 n8n 워크플로 내보내기 파일을 정규화하고, 비교하고, 점검합니다.",
    "help.lang": "메시지 출력 언어: en 또는 ko (기본값: N8N_TIDY_LANG, 그다음 LC_ALL/LC_MESSAGES/LANG)",
    "help.normalize": "내보내기 파일을 안정된 형태로 다시 씁니다 (파일 또는 폴더)",
    "help.normalize.stdout": "파일을 고치지 않고 결과를 출력합니다 (파일 하나)",
    "help.normalize.check": "아무것도 바꾸지 않고, 정규화가 필요한 파일이 있으면 종료 코드 1 로 끝납니다",
    "help.normalize.keep_pin_data": "pinData 를 유지합니다 (기본은 제거)",
    "help.normalize.keep_static_data": "staticData 를 유지합니다 (기본은 제거)",
    "help.diff": "내보내기 파일 두 개, 또는 REV 시점과 작업 트리의 의미 단위 비교",
    "help.diff.paths": "파일 두 개 A B, 또는 --rev 와 함께 PATH 하나",
    "help.diff.rev": "git 리비전 REV 시점의 PATH 를 작업 트리와 비교합니다",
    "help.diff.no_layout": "노드 위치(배치만) 변경을 숨깁니다",
    "help.diff.exit_code": "변경이 있으면 종료 코드 1 로 끝납니다",
    "help.show": "내보내기 파일의 노드 블록 리뷰 뷰를 출력합니다",
    "help.textconv": "git diff 드라이버 진입점 (show 와 같고, 실패하지 않습니다)",
    "help.check": "pinData, 정규화되지 않은 파일, 인스턴스 정보, 토큰처럼 보이는 문자열을 찾습니다",
    "help.check.allow": "해당 종류를 무시합니다 (반복 가능): {kinds}",
    "help.check.keep_static_data": "staticData 가 유지된다고 가정합니다 (`normalize --keep-static-data` 와 짝)",
    "help.install": "이 저장소의 로컬 git 설정에 diff 드라이버를 등록합니다",
    "help.install.pattern": "gitattributes 패턴 (기본값: *.json)",
    "help.install.command": "git 이 n8n-tidy 를 호출하는 방법 (기본값: n8n-tidy)",
    "help.install.dry_run": "쓰게 될 내용만 출력합니다",
    "help.uninstall": "install-git 이 쓴 내용을 제거합니다",
    "out.error": "n8n-tidy: 오류: {msg}",
    "out.skipped_not_workflow": "건너뜀: {path} (n8n 워크플로가 아님)",
    "out.skipped_invalid_json": "건너뜀: {path} (올바르지 않은 JSON)",
    "out.skipped_not_utf8": "건너뜀: {path} (UTF-8 텍스트가 아님)",
    "out.needs_normalizing": "정규화 필요: {path}",
    "out.normalized": "정규화 완료: {path}",
    "out.problems_found": "문제 {count}건을 찾았습니다.",
    "out.ok": "이상 없음: 문제를 찾지 못했습니다.",
    "out.nothing_to_remove": "제거할 항목이 없습니다.",
    "out.dry_run": "(미리 보기)",
    "err.stdout_one_file": "--stdout 은 파일을 정확히 하나만 받습니다.",
    "err.rev_one_path": "--rev 를 쓸 때는 PATH 를 정확히 하나만 지정합니다 (REV 시점과 작업 트리를 비교합니다).",
    "err.diff_two_files": "파일 두 개를 지정합니다: n8n-tidy diff A B  (또는 PATH 하나와 --rev REV).",
    "e.invalid_json": "{source}: 올바른 JSON 이 아닙니다 ({detail}). 워크플로를 다시 내보내거나 파일을 고치세요.",
    "e.not_workflow": (
        "{source}: n8n 워크플로 내보내기 파일이 아닙니다 ('nodes' 와 'connections' 를 가진 객체 또는 배열이어야 합니다)."
    ),
    "e.file_not_found": "{path}: 파일을 찾을 수 없습니다.",
    "e.cannot_read": "{path}: UTF-8 텍스트로 읽을 수 없습니다 ({detail}).",
    "e.path_not_found": "{path}: 경로를 찾을 수 없습니다.",
    "e.git_missing": "PATH 에서 git 을 찾을 수 없습니다. 먼저 git 을 설치하세요.",
    "e.git_timeout": "git {args} 명령이 {seconds}초 안에 끝나지 않았습니다.",
    "e.git_failed": "git {args} 명령이 실패했습니다: {detail}",
    "e.bad_rev": "잘못된 리비전 {rev}: '-' 로 시작할 수 없습니다.",
    "e.cannot_read_rev": (
        "파일을 읽을 수 없습니다: {path} (리비전 {rev}): {detail}. "
        "리비전이 존재하는지, 그 시점에 파일이 추적되고 있는지 확인하세요."
    ),
    "e.not_git_repo": "git 저장소 안이 아닙니다. 먼저 `git init` 을 실행한 뒤 install-git 을 다시 실행하세요.",
    "e.bad_pattern": "--pattern 은 'workflows/**/*.json' 처럼 비어 있지 않은 한 줄짜리 glob 이어야 합니다.",
    "e.empty_command": "--command 는 비어 있으면 안 됩니다.",
}

MESSAGES: dict[str, dict[str, str]] = {"en": EN, "ko": KO}


def _from_locale(value: str) -> str:
    return "ko" if value.strip().lower().startswith("ko") else "en"


def resolve_lang(cli_value: str | None = None, env: Mapping[str, str] | None = None) -> str:
    """Pick ``en`` or ``ko``: ``--lang`` > ``N8N_TIDY_LANG`` > ``LC_ALL`` > ``LC_MESSAGES`` > ``LANG``; else ``en``."""
    if cli_value in LANGS:
        return str(cli_value)
    environ = os.environ if env is None else env
    for name in (ENV_VAR, "LC_ALL", "LC_MESSAGES", "LANG"):
        value = environ.get(name, "")
        if value.strip():
            return _from_locale(value)
    return "en"


def t(lang: str, key: str, **params: object) -> str:
    """Format message ``key`` in ``lang`` (falls back to English for unknown languages)."""
    table = MESSAGES.get(lang, EN)
    return table[key].format(**params)
