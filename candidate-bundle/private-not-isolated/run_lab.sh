#!/bin/bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
LAB="$ROOT/bin/private-not-isolated-lab"
CONFIG="$ROOT/config/access-plane.json"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This exercise bundle supports macOS only." >&2
  exit 1
fi

if [[ ! -f "$LAB" ]]; then
  echo "Lab binary is missing: $LAB" >&2
  exit 1
fi

if [[ ! -x "$LAB" ]]; then
  chmod +x "$LAB"
fi

if xattr -p com.apple.quarantine "$LAB" >/dev/null 2>&1; then
  echo "macOS quarantined the downloaded lab binary."
  echo "After confirming this bundle came from the expected sender, run:"
  echo "  xattr -d com.apple.quarantine \"$LAB\""
  echo "Then run ./run_lab.sh again."
  exit 1
fi

echo "Starting candidate lab"
echo "Configuration: $CONFIG"
echo "Saved routing changes apply on the next request; no restart is required."

exec "$LAB" --config "$CONFIG"
