import re
from pathlib import Path

from n8n_tidy.cli import SUBCOMMANDS, build_parser

ROOT = Path(__file__).resolve().parent.parent


def _hooks():
    text = (ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    ids = re.findall(r"^- id: (\S+)", text, re.M)
    entries = re.findall(r"^  entry: (.+)$", text, re.M)
    return dict(zip(ids, entries))


def test_hooks_point_at_real_subcommands():
    hooks = _hooks()
    assert set(hooks) == {"n8n-tidy-check", "n8n-tidy-normalize"}
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    script = re.search(r'^(\S+) = "n8n_tidy\.cli:main"', pyproject, re.M).group(1)
    parser = build_parser()
    for hook_id, entry in hooks.items():
        prog, sub = entry.split()
        assert prog == script
        assert sub in SUBCOMMANDS
        parser.parse_args([sub, "some.json"])  # argparse accepts file arguments as pre-commit passes them
        assert hook_id == f"n8n-tidy-{sub}"


def test_subcommand_list_matches_parser():
    action = next(a for a in build_parser()._actions if getattr(a, "choices", None) and "diff" in a.choices)
    assert set(action.choices) == set(SUBCOMMANDS)


def test_version_matches_pyproject():
    import n8n_tidy

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{n8n_tidy.__version__}"' in pyproject
