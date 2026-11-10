"""Command line interface. Exit codes: 0 ok, 1 findings/changes (where requested), 2 usage or input error."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__, gitio
from .check import KINDS, check_text
from .diff import diff_documents
from .io import InvalidJSONError, NotAWorkflowError, TidyError, iter_json_files, load, parse, write_text
from .normalize import dumps, normalize
from .render import pin_data_warnings, render_json, render_md, render_text, review_view

SUBCOMMANDS = ("normalize", "diff", "show", "textconv", "check", "install-git", "uninstall-git")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="n8n-tidy", description="Normalize, diff and check n8n workflow exports for git.")
    p.add_argument("--version", action="version", version=f"n8n-tidy {__version__}")
    sub = p.add_subparsers(dest="subcommand", required=True, metavar="COMMAND")

    n = sub.add_parser("normalize", help="rewrite exports into a stable form (files or folders)")
    n.add_argument("paths", nargs="+", metavar="PATH")
    n.add_argument("--stdout", action="store_true", help="print the result instead of rewriting (one file)")
    n.add_argument("--check", action="store_true", help="change nothing; exit 1 if any file needs normalizing")
    n.add_argument("--keep-pin-data", action="store_true", help="keep pinData (removed by default)")
    n.add_argument("--keep-static-data", action="store_true", help="keep staticData (removed by default)")

    d = sub.add_parser("diff", help="semantic diff of two exports, or of REV vs the working tree")
    d.add_argument("paths", nargs="+", metavar="PATH", help="two files A B, or one PATH with --rev")
    d.add_argument("--rev", metavar="REV", help="compare PATH at git revision REV against the working tree")
    d.add_argument("--format", choices=("text", "md", "json"), default="text")
    d.add_argument("--no-layout", action="store_true", help="hide node position (layout only) changes")
    d.add_argument("--exit-code", action="store_true", help="exit 1 when there are changes")
    d.add_argument("--color", choices=("auto", "always", "never"), default="auto")

    s = sub.add_parser("show", help="print the node-block review view of an export")
    s.add_argument("file")
    t = sub.add_parser("textconv", help="git diff driver entry point (same as show, never fails)")
    t.add_argument("file")

    c = sub.add_parser("check", help="find pinData, un-normalized files, instance info, token-like strings")
    c.add_argument("paths", nargs="+", metavar="PATH")
    c.add_argument("--allow", action="append", default=[], choices=KINDS, metavar="KIND",
                   help=f"ignore a kind (repeatable): {', '.join(KINDS)}")
    c.add_argument("--keep-static-data", action="store_true",
                   help="expect staticData to be kept (matches `normalize --keep-static-data`)")

    i = sub.add_parser("install-git", help="register the diff driver in this repository's local git config")
    i.add_argument("--pattern", default="*.json", help="gitattributes pattern (default: *.json)")
    i.add_argument("--command", default="n8n-tidy", help="how git should call n8n-tidy (default: n8n-tidy)")
    i.add_argument("--dry-run", action="store_true", help="print what would be written")
    sub.add_parser("uninstall-git", help="remove what install-git wrote")
    return p


def _err(msg: str) -> int:
    print(f"n8n-tidy: error: {msg}", file=sys.stderr)
    return 2


def _skip(path: Path, exc: TidyError) -> None:
    reason = "not an n8n workflow" if isinstance(exc, NotAWorkflowError) else "invalid JSON"
    print(f"skipped: {path} ({reason})")


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
        return _err("--stdout needs exactly one file.")
    needs_change = False
    for path in files:
        try:
            workflows, is_array = load(path)
        except (NotAWorkflowError, InvalidJSONError) as exc:
            _skip(path, exc)
            continue
        except TidyError:
            if _is_binary(path):  # same as check: non-UTF-8 files are skipped, not fatal
                print(f"skipped: {path} (not UTF-8 text)")
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
            print(f"needs normalizing: {path}")
        else:
            write_text(path, text)
            print(f"normalized: {path}")
    return 1 if (args.check and needs_change) else 0


def _use_color(mode: str) -> bool:
    return mode == "always" or (mode == "auto" and sys.stdout.isatty())


def _cmd_diff(args: argparse.Namespace) -> int:
    if args.rev:
        if len(args.paths) != 1:
            return _err("with --rev give exactly one PATH (REV is compared with the working tree).")
        path = args.paths[0]
        a_docs, a_array = parse(gitio.show_revision(args.rev, path), f"{path}@{args.rev}")
        b_docs, b_array = load(path)
        a_label, b_label = f"{path}@{args.rev}", f"{path} (working tree)"
    else:
        if len(args.paths) != 2:
            return _err("give two files: n8n-tidy diff A B  (or one PATH with --rev REV).")
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
            _skip(path, exc)
        except UnicodeDecodeError:
            print(f"skipped: {path} (not UTF-8 text)")
    for p in problems:
        print(p.format())
    if problems:
        print(f"{len(problems)} problem(s) found.")
        return 1
    print("ok: no problems found.")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    for line in gitio.install(Path.cwd(), pattern=args.pattern, command=args.command, dry_run=args.dry_run):
        print(line)
    return 0


def _cmd_uninstall(_: argparse.Namespace) -> int:
    done = gitio.uninstall(Path.cwd())
    print("\n".join(done) if done else "nothing to remove.")
    return 0


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
    args = build_parser().parse_args(argv)
    try:
        return _HANDLERS[args.subcommand](args)
    except TidyError as exc:
        return _err(str(exc))
    except BrokenPipeError:  # e.g. `n8n-tidy diff ... | head`
        return 0


if __name__ == "__main__":
    sys.exit(main())
