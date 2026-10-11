#!/usr/bin/env bash
# Install everything needed to run the simulation.
#   ./setup.sh            -> creates .venv/ here and installs pygame-ce + Pillow into it
#   (with a virtualenv already active, it installs into that one instead)
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: $PYTHON not found. Install Python 3.9+ (https://www.python.org/downloads/) and re-run." >&2
  exit 1
fi

if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "error: Python 3.9+ is required, found $("$PYTHON" --version 2>&1)." >&2
  exit 1
fi

if [ -n "${VIRTUAL_ENV:-}" ]; then
  echo "Using the active virtualenv: $VIRTUAL_ENV"
  PY="$VIRTUAL_ENV/bin/python"
else
  if [ ! -x .venv/bin/python ]; then
    echo "Creating .venv/ with $("$PYTHON" --version 2>&1)"
    "$PYTHON" -m venv .venv
  fi
  PY=".venv/bin/python"
fi

"$PY" -m pip install --upgrade --quiet pip
"$PY" -m pip install --quiet -r requirements.txt

echo
echo "Done. Start the simulation with:"
if [ -n "${VIRTUAL_ENV:-}" ]; then
  echo "  python main.py"
else
  echo "  .venv/bin/python main.py"
fi
echo "It starts paused: press SPACE to run."
