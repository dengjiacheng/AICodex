#!/usr/bin/env python3
"""Initialize the `.codex` auto-task directory in the target workspace."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.auto_task.bootstrap import bootstrap_codex


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="目标工作区根目录（默认当前目录）",
    )
    args = parser.parse_args()
    root = Path(args.target).resolve()
    codex_path = bootstrap_codex(root)
    print(f"Initialized auto-task scaffolding under {codex_path}")


if __name__ == "__main__":
    main()
