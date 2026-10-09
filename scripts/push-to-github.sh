#!/bin/sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GH="$ROOT/scripts/gh"
cd "$ROOT"

if ! "$GH" auth status >/dev/null 2>&1; then
  echo "Not logged into GitHub yet. Run this first (browser will open):"
  echo "  $GH auth login"
  exit 1
fi

"$GH" repo create incident-zero --public --source=. --remote=origin --push
