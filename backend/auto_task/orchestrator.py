import asyncio
import json
import logging
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from .cli_runner import CodexCliRunner, RunOptions
from .event_handler import AutoSessionEventHandler
from .storage import AutoTaskStorage, AutoTaskStorageError
from .types import AutoTaskState, CurrentTask, TaskStatus
from .utils import load_prompt_template, render_prompt


class AutoTaskOrchestrator:
    """
    Coordinates the automated Codex loop.

    The current implementation focuses on scaffolding: it manages lifecycle
    state, websocket subscribers, and launches a placeholder worker. Actual
    task execution will be implemented in subsequent iterations.
    """

    def __init__(
        self,
        storage: AutoTaskStorage,
        runner: CodexCliRunner,
        config_provider: Optional[Callable[[], Dict[str, str]]] = None,
    ) -> None:
        self.storage = storage
        self.runner = runner
        self.state = AutoTaskState(status="idle")
        self._listeners: Set[asyncio.Queue[Dict[str, Any]]] = set()
        self._lock = asyncio.Lock()
        self._worker: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()
        self._clarification_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._thread_id: Optional[str] = None
        self._templates_base = self.storage.codex_root / "prompts"
        self._config_provider = config_provider or self._default_config_provider

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        async with self._lock:
            if self._worker and not self._worker.done():
                raise RuntimeError("Auto task orchestrator already running.")
            try:
                self.state.current_task = self.storage.load_current_task()
            except AutoTaskStorageError as exc:
                self.state.last_error = str(exc)
                await self._broadcast(
                    {"type": "alert", "level": "error", "message": str(exc)}
                )
                raise
            self.state.status = "running"
            self.state.last_error = None
            self._stop_event.clear()
            self._worker = asyncio.create_task(self._run_loop())
            await self._broadcast_state()

    async def stop(self) -> None:
        async with self._lock:
            if not self._worker:
                self.state.status = "idle"
                await self._broadcast_state()
                return
            self.state.status = "pausing"
            await self._broadcast_state()
            self._stop_event.set()

            if self._current_process and self._current_process.returncode is None:
                self._current_process.terminate()
                try:
                    await asyncio.wait_for(self._current_process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._current_process.kill()
            self._current_process = None
        if self._worker:
            await asyncio.gather(self._worker, return_exceptions=True)
        async with self._lock:
            self._worker = None
            if self._stop_event.is_set():
                self.state.status = "paused"
            else:
                self.state.status = "idle"
            await self._broadcast_state()

    def get_state(self) -> Dict[str, Any]:
        return self.state.to_dict()

    async def submit_user_clarification(self, text: str) -> None:
        task_id = self.state.current_task.id if self.state.current_task else None
        payload = {
            "type": "clarification.received",
            "task_id": task_id,
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._clarification_queue.put(payload)
        await self._broadcast(payload)

    async def register_listener(self) -> asyncio.Queue[Dict[str, Any]]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._listeners.add(queue)
        await queue.put({"type": "state", "data": self.state.to_dict()})
        return queue

    def unregister_listener(self, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        self._listeners.discard(queue)

    def set_config_provider(self, provider: Callable[[], Dict[str, str]]) -> None:
        self._config_provider = provider

    def _default_config_provider(self) -> Dict[str, str]:
        return {
            "command": "codex",
            "args": "",
            "workspace": str(self.storage.project_root),
            "model": "",
            "reasoning": "",
            "summary": "",
            "approval": "",
            "sandbox": "",
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    async def _broadcast_state(self) -> None:
        logging.info("auto-task state: %s", self.state.status)
        await self._broadcast({"type": "state", "data": self.state.to_dict()})

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        dead: Set[asyncio.Queue[Dict[str, Any]]] = set()
        for queue in self._listeners:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                dead.add(queue)
        for queue in dead:
            self._listeners.discard(queue)

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    current_task = self.storage.load_current_task()
                except AutoTaskStorageError as exc:
                    self.state.status = "error"
                    self.state.last_error = str(exc)
                    await self._broadcast_state()
                    await self._broadcast(
                        {
                            "type": "alert",
                            "level": "error",
                            "message": str(exc),
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    return

                self.state.current_task = current_task
                self.state.last_error = None

                if current_task.status == TaskStatus.DONE:
                    self.state.status = "completed"
                    await self._broadcast_state()
                    break

                self.state.status = "running"
                await self._broadcast_state()
                await self._broadcast_task_update(current_task, "running")
                await self._emit_message(current_task, role="system", kind="status", text="开始执行当前任务")

                if current_task.status == TaskStatus.FAILED:
                    self.state.status = "error"
                    await self._broadcast_state()
                    break

                if current_task.status == TaskStatus.FAILED:
                    await self._emit_message(current_task, role="system", kind="error", text="任务已标记为失败，等待人工处理")
                    self.state.status = "error"
                    await self._broadcast_state()
                    break

                if current_task.status == TaskStatus.NEEDS_CLARIFICATION:
                    await self._await_clarification(current_task)
                    if self._stop_event.is_set():
                        break
                    continue
                logging.info("auto-task: executing task %s", current_task.id)
                process_holder: List[asyncio.subprocess.Process] = []
                try:
                    execution_result = await self._execute_task(current_task, process_holder)
                except Exception as exc:  # pragma: no cover - defensive
                    await self._handle_failure(current_task, str(exc))
                    await self._emit_message(current_task, role="system", kind="error", text=f"执行过程中出现异常：{exc}")
                    break
                finally:
                    if process_holder:
                        proc = process_holder[0]
                        if proc.returncode is None:
                            proc.terminate()
                            try:
                                await asyncio.wait_for(proc.wait(), timeout=5)
                            except asyncio.TimeoutError:
                                proc.kill()
                        self._current_process = None

                status = (execution_result.get("status") or "unknown").lower()
                return_code = execution_result.get("returncode")
                payload = execution_result.get("payload") or {}

                if status == "needs_clarification":
                    current_task.status = TaskStatus.NEEDS_CLARIFICATION
                    self.storage.save_current_task(current_task)
                    await self._broadcast_task_update(
                        current_task,
                        "paused",
                        reason="needs_clarification",
                    )
                    await self._emit_message(current_task, role="system", kind="status", text="Codex 请求澄清，等待用户输入")
                    break

                if status != "success" or (return_code is not None and return_code != 0):
                    reason = payload.get("error") or execution_result.get("error") or "自动任务执行失败"
                    await self._handle_failure(current_task, reason)
                    await self._emit_message(current_task, role="system", kind="error", text=f"任务执行失败：{reason}")
                    break

                try:
                    await self._write_summary(current_task, execution_result)
                    has_next = await self._update_next_task(current_task, execution_result)
                except Exception as exc:  # pragma: no cover - defensive
                    await self._handle_failure(current_task, f"写入总结失败: {exc}")
                    await self._emit_message(current_task, role="system", kind="error", text=f"写入总结失败：{exc}")
                    break

                self.state.status = "paused"
                await self._broadcast_state()
                await self._broadcast_task_update(current_task, "success", summary=execution_result.get("summary_markdown"))
                await self._emit_message(current_task, role="system", kind="status", text="任务执行完成")

                if not has_next:
                    self.state.status = "completed"
                    await self._broadcast_state()
                    break

            # stop requested
        finally:
            self._worker = None
            if self._stop_event.is_set():
                self.state.status = "paused"
            elif self.state.status != "error":
                self.state.status = "idle"
            await self._broadcast_state()

    async def _await_clarification(self, task: CurrentTask) -> None:
        self.state.status = "waiting_clarification"
        await self._broadcast_state()
        await self._broadcast_task_update(task, "paused", reason="needs_clarification")
        try:
            while not self._stop_event.is_set():
                try:
                    payload = await asyncio.wait_for(self._clarification_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                await self._broadcast(
                    {
                        "type": "clarification.processed",
                        "task_id": task.id,
                        "text": payload.get("text"),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
                task.status = TaskStatus.PENDING
                self.storage.save_current_task(task)
                return
        except asyncio.CancelledError:
            raise

    async def _emit_message(self, task: CurrentTask, *, role: str, kind: str, text: str) -> None:
        message = {
            "id": str(uuid4()),
            "role": role,
            "kind": kind,
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._broadcast({"type": "auto_task.message", "task_id": task.id, "message": message})

    async def _broadcast_task_update(self, task: CurrentTask, status: str, **extra: Any) -> None:
        payload = {
            "type": "task.update",
            "task_id": task.id,
            "status": status,
            "attempts": self.state.attempts,
            "title": task.title,
            "objective": task.objective,
        }
        payload.update(extra)
        await self._broadcast(payload)

    async def _execute_task(self, task: CurrentTask, process_holder: Optional[List[asyncio.subprocess.Process]] = None) -> Dict[str, Any]:
        # 加载 Prompt 模板
        template = load_prompt_template(self._templates_base, "task_executor")

        # 构建上下文
        task_dict = task.to_dict()
        knowledge_summary = self._build_knowledge_summary(task)
        context: Dict[str, Any] = {
            "task_json": json.dumps(task_dict, ensure_ascii=False, indent=2),
            "knowledge_summary": knowledge_summary,
            "recent_diffs": "",
            "workspace_state": json.dumps(self._snapshot_workspace(task), ensure_ascii=False, indent=2),
            "task": task_dict,
            "task.id": task.id,
            "task.title": task.title,
            "task.objective": task.objective,
            "task.workdir": task.workdir,
        }

        prompt_content = render_prompt(template, context)

        config = self._config_provider()
        command = (config.get("command") or "codex").strip() or "codex"
        args_text = config.get("args") or ""
        args = shlex.split(args_text) if args_text else []
        workspace_setting = config.get("workspace") or str(self.storage.project_root)
        workspace_root = Path(workspace_setting).expanduser()
        workspace = (workspace_root / task.workdir).resolve() if task.workdir else workspace_root

        options = RunOptions(
            workspace=workspace,
            command=command,
            args=args,
            thread_id=self._thread_id,
            model=config.get("model") or None,
            sandbox=config.get("sandbox") or None,
            reasoning=config.get("reasoning") or None,
            summary_style=config.get("summary") or None,
            approval=config.get("approval") or None,
            prompt_argument=prompt_content.strip() or None,
        )

        if process_holder is None:
            process_holder = []

        handler = AutoSessionEventHandler(self, task, process_holder)
        async for event in self.runner.run(options, process_holder):
            await handler.handle(event)
        result = handler.finalize()
        self._current_process = None
        return result

    @staticmethod
    def _build_cli_message(role: str, kind: str, text: str, timestamp: str) -> Dict[str, Any]:
        return {
            "id": str(uuid4()),
            "role": role,
            "kind": kind,
            "text": text,
            "timestamp": timestamp,
        }

    def _build_knowledge_summary(self, task: CurrentTask) -> str:
        overview = (self.storage.codex_root / "knowledge" / "overview.md")
        roadmap = (self.storage.codex_root / "knowledge" / "roadmap.md")
        base = self.storage.codex_root / "knowledge"
        sections: List[str] = []
        if base.exists():
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                relative = path.relative_to(self.storage.codex_root)
                sections.append(f"--- FILE: {relative.as_posix()}\n{content}")
        return "\n\n".join(sections)

    def _snapshot_workspace(self, task: CurrentTask) -> Dict[str, Any]:
        # 占位实现：真实实现应当运行 `git status` 等命令
        return {
            "workdir": task.workdir,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _write_summary(self, task: CurrentTask, result: Dict[str, Any]) -> None:
        markdown = result.get("summary_markdown") or "（尚未提供总结）"
        self.storage.write_task_summary(task.id, markdown)
        payload = result.get("payload", {})
        knowledge_updates = payload.get("knowledge_updates") or []
        applied_updates = []
        for item in knowledge_updates:
            path = item.get("path")
            content = item.get("content")
            summary = item.get("summary")
            if path and content:
                self.storage.write_knowledge_file(path, content)
                applied_updates.append({"path": path, "summary": summary, "written": True})
            elif path:
                applied_updates.append({"path": path, "summary": summary, "written": False})
        await self._broadcast(
            {
                "type": "summary.ready",
                "task_id": task.id,
                "markdown": markdown,
                "tests": payload.get("tests"),
                "knowledge_updates": applied_updates,
            }
        )
        if applied_updates:
            await self._broadcast(
                {
                    "type": "knowledge.updated",
                    "task_id": task.id,
                    "updates": applied_updates,
                }
            )

    async def _update_next_task(self, task: CurrentTask, result: Dict[str, Any]) -> bool:
        payload = result.get("payload") or {}
        handoff = payload.get("next_task")
        if not handoff:
            task.status = TaskStatus.DONE
            self.storage.save_current_task(task)
            return False
        next_task = CurrentTask.from_dict(handoff)
        self.storage.save_current_task(next_task)
        self.state.current_task = next_task
        await self._broadcast_task_update(next_task, "pending")
        return True

    async def _handle_failure(self, task: CurrentTask, reason: str) -> None:
        task.status = TaskStatus.FAILED
        self.storage.save_current_task(task)
        self.state.status = "error"
        self.state.last_error = reason
        await self._broadcast_state()
        await self._broadcast_task_update(task, "failed", error=reason)
        await self._emit_message(task, role="system", kind="error", text=f"任务失败：{reason}")
        alert = {
            "type": "alert",
            "level": "error",
            "message": reason,
            "task_id": task.id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._broadcast(alert)
        self.storage.record_alert(alert)
