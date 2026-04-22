#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
pip install -q -r requirements.txt
python -m src.main "$@"
