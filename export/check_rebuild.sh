#!/bin/bash
# Offline rebuild check: rebuild the DB and the export from data/raw-derived JSON (data/docs, data/brod/docs) and
# the transcripts, without network, into a scratch copy under data/tmp/rebuild-check-*, then compare its export
# hashes with the published data/export/export_sha256.txt. The live data/vijecnica.db and data/export are never
# written (build.py / export.py take VIJECNICA_DB and VIJECNICA_EXPORT_OUT).
# Usage: export/check_rebuild.sh [--keep]   (exit 0 = identical CSVs; --keep leaves the scratch copy for inspection)
# Note: if transcripts or docs changed since the last live build + export, a difference is expected.
set -eu
cd "$(dirname "$0")/.."
PY=.venv/bin/python
WORK=$(mktemp -d "$PWD/data/tmp/rebuild-check-XXXXXX")
[ "${1:-}" = "--keep" ] || trap 'rm -rf "$WORK"' EXIT
export VIJECNICA_DB="$WORK/vijecnica.db" VIJECNICA_EXPORT_OUT="$WORK/export"
$PY db/build.py > "$WORK/build.log"
$PY export/export.py > "$WORK/export.log"
if diff data/export/export_sha256.txt "$WORK/export/export_sha256.txt"; then
  echo "export identical (scratch: $WORK)"
else
  echo "export differs from data/export/export_sha256.txt (scratch: $WORK)"
  exit 1
fi
