#!/usr/bin/env bash
set -euo pipefail

python3 - "$@" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

files = [Path(arg) for arg in sys.argv[1:]]
if not files:
    files = [Path(".env.example"), Path(".env.real-canary.example"), Path(".env.real.example")]
key_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
embedded_key_re = re.compile(r"\s+[A-Za-z_][A-Za-z0-9_]*=")
failed = False

for path in files:
    if not path.exists():
        print(f"ok {path} missing; skipped")
        continue

    seen: dict[str, int] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            print(f"{path}:{lineno}: export is not allowed; use KEY=VALUE", file=sys.stderr)
            failed = True
            continue

        if not key_re.match(line):
            print(f"{path}:{lineno}: invalid env line: {raw!r}", file=sys.stderr)
            failed = True
            continue

        key, value = line.split("=", 1)
        if key in seen:
            print(f"{path}:{lineno}: duplicate key {key!r}; first seen on line {seen[key]}", file=sys.stderr)
            failed = True
        seen[key] = lineno

        if re.search(r"\s+#", value):
            print(f"{path}:{lineno}: inline comments are not allowed; put comments on their own line", file=sys.stderr)
            failed = True

        if embedded_key_re.search(value):
            print(f"{path}:{lineno}: multiple KEY=VALUE assignments on one line are not allowed", file=sys.stderr)
            failed = True

    print(f"ok {path}")

if failed:
    raise SystemExit(1)
PY
