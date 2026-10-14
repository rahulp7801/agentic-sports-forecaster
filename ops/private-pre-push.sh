#!/bin/sh
# Install this hook only in the dedicated private research checkout.
set -eu
root="$(git rev-parse --show-toplevel)"
if test -f "$root/.venv/Scripts/python.exe"; then
    python="$root/.venv/Scripts/python.exe"
elif test -f "$root/.venv/bin/python"; then
    python="$root/.venv/bin/python"
else
    echo 'Private publication blocked: checkout Python runtime is missing' >&2
    exit 1
fi
exec "$python" -S "$root/ops/verify_private_push.py" "$@"
