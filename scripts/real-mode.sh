#!/usr/bin/env bash
# Real mode: reproduce the tool's premise against a real n8n (docker image n8nio/n8n:2.46.7).
# Not run by CI. First run pulls the image (a few minutes); needs docker and network.
# Usage: scripts/real-mode.sh
set -euo pipefail

IMAGE="n8nio/n8n:2.46.7"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/in" "$WORK/e1" "$WORK/e2" "$WORK/e3" "$WORK/e4"
cp "$HERE/examples/export-before.json" "$WORK/in/before.json"
cp "$HERE/examples/export-after.json" "$WORK/in/after.json"
chmod -R a+rwX "$WORK"

# One container run: import before -> export (e1, e2) -> re-import -> export (e3) -> import after -> export (e4).
docker run --rm --label n8n-tidy -v "$WORK:/data" --entrypoint sh "$IMAGE" -c '
  set -e
  n8n import:workflow --input=/data/in/before.json
  n8n export:workflow --backup --output=/data/e1/
  n8n export:workflow --backup --output=/data/e2/
  n8n import:workflow --separate --input=/data/e1/
  n8n export:workflow --backup --output=/data/e3/
  n8n import:workflow --input=/data/in/after.json
  n8n export:workflow --backup --output=/data/e4/
'

TIDY="uv run --project $HERE n8n-tidy"
for e in e1 e2 e3 e4; do
  echo "$e normalized sha256: $($TIDY normalize --stdout "$WORK/$e"/*.json | shasum -a 256 | cut -d' ' -f1)"
done
echo "--- diff e1 -> e4"
$TIDY diff "$WORK"/e1/*.json "$WORK"/e4/*.json || true
