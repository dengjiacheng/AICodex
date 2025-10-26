from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class GlobalConfig:
    command: str = field(default_factory=lambda: _env_value_or_default("CODEX_CMD", "codex"))
    args: str = ""
    workspace: str = field(default_factory=lambda: _env_value_or_default("REPO_ROOT", str(Path.cwd())))
    model: str = "gpt-5-codex"
    reasoning: str = "high"
    summary: str = "auto"
    approval: str = "never"
    sandbox: str = "danger-full-access"

    def as_state(self) -> Dict[str, str]:
        return {
            "command": self.command,
            "args": self.args,
            "workspace": self.workspace,
            "model": self.model,
            "reasoning": self.reasoning,
            "summary": self.summary,
            "approval": self.approval,
            "sandbox": self.sandbox,
        }

    def update(self, updates: Dict[str, Optional[str]]) -> None:
        for key, value in updates.items():
            if value is None:
                continue
            if key == "command":
                stripped = value.strip()
                if not stripped:
                    raise ValueError("命令不能为空")
                self.command = stripped
            elif key == "workspace":
                resolved = str(Path(value).expanduser().resolve()) if value else self.workspace
                self.workspace = resolved
            elif hasattr(self, key):
                setattr(self, key, value or getattr(self, key))


def _env_value_or_default(key: str, fallback: str) -> str:
    value = os.environ.get(key)
    if not value:
        return fallback
    trimmed = value.strip()
    return trimmed or fallback
