"""
Auto task orchestration package.

This namespace hosts the building blocks required to run the automated Codex
task loop:
- storage helpers for `.codex/` assets
- CLI runner abstraction
- orchestrator state machine
- FastAPI router exposing control endpoints
"""

__all__ = [
    "cli_runner",
    "orchestrator",
    "router",
    "storage",
    "types",
]
