# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-10

### Added
- `normalize`: idempotent normalization of workflow exports (volatile fields, `pinData`, `shared`, `meta.instanceId`), folders, array exports, `--check`, `--stdout`.
- `diff`: semantic diff of two files or of a git revision against the working tree (`--rev`), text/markdown/json output, `--exit-code`.
- `show` / `textconv`: node-block review view for `git diff`.
- `check`: `pin-data`, `not-normalized`, `instance-info` and `secret-suspect` findings with masked tokens.
- `install-git` / `uninstall-git`: diff driver in the repository's local git config only.
- `.pre-commit-hooks.yaml` with `n8n-tidy-check` and `n8n-tidy-normalize`.
