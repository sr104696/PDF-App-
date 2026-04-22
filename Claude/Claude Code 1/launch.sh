#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  PDF Intelligence v2 — Linux / macOS launch script
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR"
exec python3 -OO -B -m src.main "$@"
