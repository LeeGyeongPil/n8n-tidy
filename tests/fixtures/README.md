# Test fixtures (practice mocks)

These files are **hand-written mock exports**, not real n8n output.

- The envelope (top-level fields, volatile fields, `shared`, `meta.instanceId`, `versionMetadata`) imitates what
  `n8n export:workflow --backup` writes in n8n 2.46.7.
- Node contents (names, prompts, parameters) were written from scratch for this project. Ids, project ids and
  instance ids are obviously fake; addresses use `example.com`.
- They reproduce observed behaviour: re-importing changes only `versionId`, `versionCounter` and `updatedAt`
  (`export-v1` vs `export-v1-reimported`); a real edit adds a prompt line, moves a node, renames a node and pins data
  (`export-v1` vs `export-v2`).
- No token-like strings are committed; tests assemble them at run time.

Regenerate with `python scripts/make_fixtures.py`.
