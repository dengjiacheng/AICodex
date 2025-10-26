import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .bootstrap import bootstrap_codex
from .types import AutoTaskState, CurrentTask


class AutoTaskStorageError(RuntimeError):
    """Raised when `.codex` storage cannot be accessed."""


class AutoTaskStorage:
    """
    Helper for reading/writing `.codex` assets.

    The implementation favours simple atomic file operations so that the
    orchestrator can run without an additional database.
    """

    CODex_DIR_NAME = ".codex"
    TASKS_DIR = "tasks"
    HISTORY_DIR = "history"
    KNOWLEDGE_DIR = "knowledge"

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.codex_root = self.project_root / self.CODex_DIR_NAME

    # --------------------------------------------------------------------- #
    # Directory preparation
    # --------------------------------------------------------------------- #
    async def ensure_structure(self) -> None:
        """Create required directories if they do not exist."""

        structure: Iterable[Path] = (
            self.codex_root / "knowledge",
            self.codex_root / "knowledge" / "modules",
            self.codex_root / "knowledge" / "apis",
            self.codex_root / "knowledge" / "tasks",
            self.codex_root / "knowledge" / "diffs",
            self.codex_root / "tasks",
            self.codex_root / "tasks" / "archive",
            self.codex_root / "history",
            self.codex_root / "history" / "sessions",
            self.codex_root / "history" / "alerts",
            self.codex_root / "history" / "metrics",
            self.codex_root / "prompts",
        )
        for directory in structure:
            directory.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------------- #
    # Task management
    # --------------------------------------------------------------------- #
    def load_current_task(self) -> CurrentTask:
        path = self.codex_root / self.TASKS_DIR / "current.json"
        if not path.exists():
            raise AutoTaskStorageError(
                f"Missing current task file at {path}. Please run bootstrap."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return CurrentTask.from_dict(data)

    def save_current_task(self, task: CurrentTask) -> None:
        path = self.codex_root / self.TASKS_DIR / "current.json"
        task.updated_at = datetime.utcnow()
        payload = json.dumps(task.to_dict(), ensure_ascii=False, indent=2)
        self._atomic_write(path, payload)

    # --------------------------------------------------------------------- #
    # History / alerts helpers
    # --------------------------------------------------------------------- #
    def append_session_event(self, task_id: str, event: Dict[str, Any]) -> None:
        directory = self.codex_root / self.HISTORY_DIR / "sessions"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{task_id}.jsonl"
        line = json.dumps(event, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def record_alert(self, event: Dict[str, Any]) -> Path:
        directory = self.codex_root / self.HISTORY_DIR / "alerts"
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = directory / f"{timestamp}.json"
        payload = json.dumps(event, ensure_ascii=False, indent=2)
        self._atomic_write(path, payload)
        return path

    def persist_state_snapshot(self, state: AutoTaskState) -> None:
        directory = self.codex_root / self.HISTORY_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "last_state.json"
        payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
        self._atomic_write(path, payload)

    # ------------------------------------------------------------------ #
    # Task archive helpers
    # ------------------------------------------------------------------ #
    def write_task_summary(self, task_id: str, markdown: str) -> Path:
        directory = self.codex_root / self.TASKS_DIR / "archive"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{task_id}.md"
        self._atomic_write(path, markdown, text=True)
        return path

    # --------------------------------------------------------------------- #
    # Knowledge helpers
    # --------------------------------------------------------------------- #
    def write_knowledge_file(self, relative_path: str, content: str) -> Path:
        """
        Write knowledge file under `.codex/knowledge`.

        Parameters
        ----------
        relative_path: str
            Path relative to the knowledge directory (e.g. "modules/api.md").
        content: str
            Full file content to store.
        """

        base = self.codex_root / self.KNOWLEDGE_DIR
        target = (base / relative_path).resolve()
        if not str(target).startswith(str(base.resolve())):
            raise AutoTaskStorageError("Knowledge path escapes base directory.")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, content, text=True)
        return target

    # --------------------------------------------------------------------- #
    # Internal utilities
    # --------------------------------------------------------------------- #
    def _atomic_write(self, path: Path, payload: str, *, text: bool = True) -> None:
        """Write file atomically using a temporary file."""
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        mode = "w" if text else "wb"
        with tmp_path.open(mode, encoding="utf-8" if text else None) as handle:
            handle.write(payload)
        tmp_path.replace(path)

    # ------------------------------------------------------------------ #
    # Bootstrap helpers
    # ------------------------------------------------------------------ #
    def bootstrap_workspace(self, workspace: Path) -> Path:
        resolved = Path(workspace).expanduser().resolve()
        self.project_root = resolved
        self.codex_root = resolved / self.CODex_DIR_NAME
        return bootstrap_codex(resolved)
