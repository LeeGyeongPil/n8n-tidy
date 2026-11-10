# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.3] - 2026-11-11

### Fixed
- `check`: added `--keep-static-data`, the counterpart of `normalize --keep-static-data`. Without it, `check` reported `not-normalized` for a file that `normalize --keep-static-data` had just written.

### Known limitations
- If the same token appears twice in one value without overlapping, the same finding line is printed twice.
- The test for an empty `staticData` with `--keep-static-data` does not isolate the cause of the failing exit code.
- Running the test suite after normalizing `examples/export-after.json` in place makes one example-based test fail (restore the file first).
- A token split by `{{ }}` is not a literal token and is not detected.

## [0.1.2] - 2026-11-11

### Fixed
- `check`: a value such as `Bearer sk-...` that matched two token patterns is now reported once instead of twice.

### Known limitations
- If the same token appears twice in one value without overlapping, the same finding line is printed twice.

## [0.1.1] - 2026-11-11

### Fixed
- `check`: `secret-suspect` now also detects tokens written in an expression value (`=...`) outside closed `{{ ... }}` parts, and after an unclosed `{{`. Previously every value starting with `=` was skipped.

### Known limitations
- A value that matches two patterns (for example `Bearer sk-...`) is reported twice at the same path with the same mask (since 0.1.0).
- A token split by `{{ }}` is not a literal token and is not detected.

## [0.1.0] - 2026-11-10

### Added
- `normalize`: idempotent normalization of workflow exports (volatile fields, `pinData`, `shared`, `meta.instanceId`), folders, array exports, `--check`, `--stdout`.
- `diff`: semantic diff of two files or of a git revision against the working tree (`--rev`), text/markdown/json output, `--exit-code`.
- `show` / `textconv`: node-block review view for `git diff`.
- `check`: `pin-data`, `not-normalized`, `instance-info` and `secret-suspect` findings with masked tokens.
- `install-git` / `uninstall-git`: diff driver in the repository's local git config only.
- `.pre-commit-hooks.yaml` with `n8n-tidy-check` and `n8n-tidy-normalize`.
