"""Command line interface. Exit codes: 0 ok, 1 findings/changes (where requested), 2 usage or input error."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__, gitio
from .check import KINDS, check_text
from .diff import diff_documents
from .i18n import LANGS, MESSAGES, resolve_lang, t
from .io import InvalidJSONError, NotAWorkflowError, TidyError, iter_json_files, load, parse, write_text
from .normalize import dumps, normalize
from .render import pin_data_warnings, render_json, render_md, render_text, review_view

SUBCOMMANDS = ("normalize", "diff", "show", "textconv", "check", "install-git", "uninstall-git")


class _QuietParser(argparse.ArgumentParser):
    """Pre-parser that never prints or exits: the real parser reports bad input exactly once."""

    def error(self, message: str):  # type: ignore[override]
        raise ValueError(message)


def _pre_parse_lang(argv: Sequence[str]) -> str | None:
    pre = _QuietParser(add_help=False, allow_abbrev=False)
    pre.add_argument("--lang")
    try:
        known, _ = pre.parse_known_args(list(argv))
    except ValueError:
        return None
    return known.lang


def build_parser(lang: str = "en") -> argparse.ArgumentParser:
    def m(key: str, **params: object) -> str:
        return t(lang, key, **params)

    # --lang is accepted before or after the sub-command; SUPPRESS keeps one value from clobbering the other.
    lang_opt = argparse.ArgumentParser(add_help=False)
    lang_opt.add_argument("--lang", choices=LANGS, default=argparse.SUPPRESS, metavar="{en,ko}", help=m("help.lang"))

    p = argparse.ArgumentParser(prog="n8n-tidy", description=m("help.description"), parents=[lang_opt])
    p.add_argument("--version", action="version", version=f"n8n-tidy {__version__}")
    sub = p.add_subparsers(dest="subcommand", required=True, metavar="COMMAND")

    n = sub.add_parser("normalize", help=m("help.normalize"), parents=[lang_opt])
    n.add_argument("paths", nargs="+", metavar="PATH")
    n.add_argument("--stdout", action="store_true", help=m("help.normalize.stdout"))
    n.add_argument("--check", action="store_true", help=m("help.normalize.check"))
    n.add_argument("--keep-pin-data", action="store_true", help=m("help.normalize.keep_pin_data"))
    n.add_argument("--keep-static-data", action="store_true", help=m("help.normalize.keep_static_data"))

    d = sub.add_parser("diff", help=m("help.diff"), parents=[lang_opt])
    d.add_argument("paths", nargs="+", metavar="PATH", help=m("help.diff.paths"))
    d.add_argument("--rev", metavar="REV", help=m("help.diff.rev"))
    d.add_argument("--format", choices=("text", "md", "json"), default="text")
    d.add_argument("--no-layout", action="store_true", help=m("help.diff.no_layout"))
    d.add_argument("--exit-code", action="store_true", help=m("help.diff.exit_code"))
    d.add_argument("--color", choices=("auto", "always", "never"), default="auto")

    s = sub.add_parser("show", help=m("help.show"), parents=[lang_opt])
    s.add_argument("file")
    tc = sub.add_parser("textconv", help=m("help.textconv"), parents=[lang_opt])
    tc.add_argument("file")

    c = sub.add_parser("check", help=m("help.check"), parents=[lang_opt])
    c.add_argument("paths", nargs="+", metavar="PATH")
    c.add_argument("--allow", action="append", default=[], choices=KINDS, metavar="KIND",
                   help=m("help.check.allow", kinds=", ".join(KINDS)))
    c.add_argument("--keep-static-data", action="store_true", help=m("help.check.keep_static_data"))

    i = sub.add_parser("install-git", help=m("help.install"), parents=[lang_opt])
    i.add_argument("--pattern", default="*.json", help=m("help.install.pattern"))
    i.add_argument("--command", default="n8n-tidy", help=m("help.install.command"))
    i.add_argument("--dry-run", action="store_true", help=m("help.install.dry_run"))
    sub.add_parser("uninstall-git", help=m("help.uninstall"), parents=[lang_opt])
    return p


def _err(lang: str, msg: str) -> int:
    print(t(lang, "out.error", msg=msg), file=sys.stderr)
    return 2


def _err_key(lang: str, key: str) -> int:
    return _err(lang, t(lang, key))


def _tidy_message(lang: str, exc: TidyError) -> str:
    """Localized text for a library error; falls back to the English ``str(exc)``."""
    key = f"e.{exc.code}" if exc.code else ""
    if key in MESSAGES.get(lang, {}):
        try:
            return t(lang, key, **exc.params)
        except (KeyError, IndexError):
            pass
    return str(exc)


def _skip(lang: str, path: Path, exc: TidyError) -> None:
    key = "out.skipped_not_workflow" if isinstance(exc, NotAWorkflowError) else "out.skipped_invalid_json"
    print(t(lang, key, path=path))


def _is_binary(path: Path) -> bool:
    try:
        path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return True
    except OSError:
        return False
    return False


def _cmd_normalize(args: argparse.Namespace) -> int:
    files = iter_json_files(args.paths)
    if args.stdout and len(files) != 1:
        return _err_key(args.ui_lang, "err.stdout_one_file")
    needs_change = False
    for path in files:
        try:
            workflows, is_array = load(path)
        except (NotAWorkflowError, InvalidJSONError) as exc:
            _skip(args.ui_lang, path, exc)
            continue
        except TidyError:
            if _is_binary(path):  # same as check: non-UTF-8 files are skipped, not fatal
                print(t(args.ui_lang, "out.skipped_not_utf8", path=path))
                continue
            raise
        normalized = [normalize(w, keep_pin_data=args.keep_pin_data, keep_static_data=args.keep_static_data)
                      for w in workflows]
        text = dumps(normalized if is_array else normalized[0])
        if args.stdout:
            sys.stdout.write(text)
            continue
        if text == path.read_text(encoding="utf-8"):
            continue
        needs_change = True
        if args.check:
            print(t(args.ui_lang, "out.needs_normalizing", path=path))
        else:
            write_text(path, text)
            print(t(args.ui_lang, "out.normalized", path=path))
    return 1 if (args.check and needs_change) else 0


def _use_color(mode: str) -> bool:
    return mode == "always" or (mode == "auto" and sys.stdout.isatty())


def _cmd_diff(args: argparse.Namespace) -> int:
    if args.rev:
        if len(args.paths) != 1:
            return _err_key(args.ui_lang, "err.rev_one_path")
        path = args.paths[0]
        a_docs, a_array = parse(gitio.show_revision(args.rev, path), f"{path}@{args.rev}")
        b_docs, b_array = load(path)
        a_label, b_label = f"{path}@{args.rev}", f"{path} (working tree)"
    else:
        if len(args.paths) != 2:
            return _err_key(args.ui_lang, "err.diff_two_files")
        a_docs, a_array = load(args.paths[0])
        b_docs, b_array = load(args.paths[1])
        a_label, b_label = args.paths
    changes = diff_documents(a_docs, b_docs)
    if args.no_layout:
        changes = [c for c in changes if c.kind != "layout"]
    warnings = pin_data_warnings(a_docs, b_docs)
    multi = a_array or b_array
    if args.format == "json":
        out = render_json(changes, warnings, a_label, b_label)
    elif args.format == "md":
        out = render_md(changes, warnings, a_label, b_label, multi=multi)
    else:
        out = render_text(changes, warnings, a_label, b_label, color=_use_color(args.color), multi=multi)
    sys.stdout.write(out)
    return 1 if (args.exit_code and changes) else 0


def _cmd_show(args: argparse.Namespace) -> int:
    workflows, _ = load(args.file)
    sys.stdout.write(review_view(workflows))
    return 0


def _cmd_textconv(args: argparse.Namespace) -> int:
    # git must always get something to diff: fall back to the raw file when it is not a workflow.
    path = Path(args.file)
    try:
        workflows, _ = load(path)
        sys.stdout.write(review_view(workflows))
    except TidyError:
        sys.stdout.write(path.read_text(encoding="utf-8", errors="replace"))
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    problems = []
    for path in iter_json_files(args.paths):
        try:
            text = path.read_text(encoding="utf-8")
            problems += check_text(text, str(path), args.allow, keep_static_data=args.keep_static_data)
        except (NotAWorkflowError, InvalidJSONError) as exc:
            _skip(args.ui_lang, path, exc)
        except UnicodeDecodeError:
            print(t(args.ui_lang, "out.skipped_not_utf8", path=path))
    for p in problems:
        print(p.format())
    if problems:
        print(t(args.ui_lang, "out.problems_found", count=len(problems)))
        return 1
    print(t(args.ui_lang, "out.ok"))
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    for line in gitio.install(Path.cwd(), pattern=args.pattern, command=args.command, dry_run=args.dry_run):
        # Only the "(dry run)" marker is CLI wording; the git configuration lines are printed as-is.
        if line.startswith(_DRY_RUN_EN):
            line = t(args.ui_lang, "out.dry_run") + line[len(_DRY_RUN_EN):]
        print(line)
    return 0


def _cmd_uninstall(args: argparse.Namespace) -> int:
    done = gitio.uninstall(Path.cwd())
    print("\n".join(done) if done else t(args.ui_lang, "out.nothing_to_remove"))
    return 0


_DRY_RUN_EN = "(dry run)"

_HANDLERS = {
    "normalize": _cmd_normalize,
    "diff": _cmd_diff,
    "show": _cmd_show,
    "textconv": _cmd_textconv,
    "check": _cmd_check,
    "install-git": _cmd_install,
    "uninstall-git": _cmd_uninstall,
}


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    lang = resolve_lang(_pre_parse_lang(argv))
    args = build_parser(lang).parse_args(argv)
    # A valid --lang seen by the real parser wins (same value the pre-parser found).
    args.ui_lang = resolve_lang(getattr(args, "lang", None))
    try:
        return _HANDLERS[args.subcommand](args)
    except TidyError as exc:
        return _err(args.ui_lang, _tidy_message(args.ui_lang, exc))
    except BrokenPipeError:  # e.g. `n8n-tidy diff ... | head`
        return 0


if __name__ == "__main__":
    sys.exit(main())
