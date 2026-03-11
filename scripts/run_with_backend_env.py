#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: run_with_backend_env.py <command> [args...]")

    root = Path(__file__).resolve().parents[1]
    backend = root / "mos" / "backend"

    # Match app.config dotenv loading so the launched process resolves models and
    # credentials the same way the backend does during import time.
    load_dotenv(root / ".env", override=False)
    load_dotenv(root / ".env.local.consolidated", override=False)
    load_dotenv(backend / ".env", override=False)

    command = sys.argv[1:]
    os.execvpe(command[0], command, os.environ.copy())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
