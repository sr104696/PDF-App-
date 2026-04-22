#!/usr/bin/env bash
cd "$(dirname "$0")"
exec python3 -OO -B -m src.main "$@"
