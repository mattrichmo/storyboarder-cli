#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install .
printf '\nInstalled. Start with:\n  .venv/bin/storyboarder ui --workspace ./stories\n'
