from __future__ import annotations

import asyncio
import datetime as dt
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from asyncio.subprocess import Process

from backend.codex_client import CodexExecConfig, consume_events

from .dispatcher import (
    ManualSessionEventAdapter,
    SessionEvent,
    SessionLifecycleEvent,
    SessionMessageEvent,
    SessionTokenEvent,
)
from .errors import (
    CommandUnavailableError,
    InvalidSessionInputError,
    ManualSessionError,
    SessionConflictError,
    SessionNotFoundError,
    WorkspaceNotFoundError,
)
from .models import AppState, ChatMessage, ConfigState, MessagePart, RoleTemplate, SessionRecord
from .transport import SessionTransport


def _env_value_or_default(key: str, fallback: str) -> str:
    value = os.environ.get(key)
    if not value:
        return fallback
    trimmed = value.strip()
    return trimmed or fallback


class ManualSessionManager:
    """
    Core manual session orchestration component.

    Responsibilities:
    - manage session lifecycle and configuration
    - dispatch Codex events via ManualSessionEventAdapter
    - interact with websocket transport
    """

    def __init__(self, transport: Optional[SessionTransport] = None) -> None:
        self.transport = transport or SessionTransport()
        self.sessions: Dict[str, SessionRecord] = {}
        self.role_templates: List[RoleTemplate] = [
            RoleTemplate(
                id="engineer",
                name="工程师",
                color="#3f51b5",
                description="负责实现功能与修复问题。",
            ),
            RoleTemplate(
                id="reviewer",
                name="审阅者",
                color="#009688",
                description="负责审阅和反馈代码变更。",
            ),
            RoleTemplate(
                id="qa",
                name="测试",
                color="#ff7043",
                description="负责质量验证与场景演练。",
            ),
        ]
        self._broadcast_state_lock = asyncio.Lock()
        self._workspace_path: str = _env_value_or_default(
            "REPO_ROOT", str(Path.cwd())
        )
        self.default_command: str = _env_value_or_default("CODEX_CMD", "codex")
        self._resolved_path_env: Optional[str] = None
        self.global_config: Dict[str, str] = {
            "command": self.default_command,
            "args": "",
            "workspace": self.workspace_path,
            "model": "gpt-5-codex",
            "reasoning": "high",
            "summary": "auto",
            "approval": "never",
            "sandbox": "danger-full-access",
        }

    # ------------------------------------------------------------------ #
    # Public properties & helpers
    # ------------------------------------------------------------------ #
    @property
    def workspace_path(self) -> str:
        return self._workspace_path

    def now_iso(self) -> str:
        return (
            dt.datetime.now(dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def serialize(self) -> AppState:
        return AppState(
            workspace=self.workspace_path,
            config=ConfigState(**self.global_config),
            role_templates=self.role_templates,
            sessions=[session.serialize() for session in self.sessions.values()],
        )

    def get_auto_task_config(self) -> Dict[str, str]:
        return dict(self.global_config)

    # ------------------------------------------------------------------ #
    # Session lifecycle methods
    # ------------------------------------------------------------------ #
    async def create_session(self, payload: Dict[str, Optional[str]]) -> SessionRecord:
        role_id = payload.get("role_id")
        template = next(
            (role for role in self.role_templates if role.id == role_id),
            None,
        )
        if template is None:
            raise SessionNotFoundError("角色模板不存在")
        role_info = template.model_dump()
        if payload.get("name"):
            role_info["name"] = payload["name"] or role_info.get("name")
        if payload.get("color"):
            role_info["color"] = payload["color"] or role_info.get("color")
        session_id = str(uuid.uuid4())
        cfg = self.global_config
        session = SessionRecord(
            id=session_id,
            role=role_info,
            command=cfg["command"],
            workspace=cfg["workspace"],
            args=cfg["args"],
            model=cfg["model"],
            reasoning=cfg["reasoning"],
            summary=cfg["summary"],
            approval=cfg["approval"],
            sandbox=cfg["sandbox"],
        )
        self.sessions[session_id] = session
        await self.transport.broadcast(
            {"type": "session_created", "session": session.serialize()}
        )
        await self._broadcast_state()
        return session

    async def update_session(
        self, session_id: str, payload: Dict[str, Optional[str]]
    ) -> SessionRecord:
        session = self._get_session(session_id)
        if payload.get("command") is not None:
            session.command = payload["command"].strip() if payload["command"] else ""
        if payload.get("args") is not None:
            session.args = payload["args"] or ""
        if payload.get("workspace") is not None:
            session.workspace = payload["workspace"] or ""
        if payload.get("model") is not None:
            session.model = payload["model"] or session.model
        if payload.get("reasoning") is not None:
            session.reasoning = payload["reasoning"] or session.reasoning
        if payload.get("summary") is not None:
            session.summary = payload["summary"] or session.summary
        if payload.get("approval") is not None:
            session.approval = payload["approval"] or session.approval
        if payload.get("sandbox") is not None:
            session.sandbox = payload["sandbox"] or session.sandbox
        await self.transport.broadcast(
            {"type": "session_updated", "session": session.serialize()}
        )
        await self._broadcast_state()
        return session

    async def start_session(self, session_id: str) -> SessionRecord:
        session = self._get_session(session_id)
        async with session.lock:
            session.status = "starting"
            session.status_detail = "正在检查命令…"
        await self._broadcast_state()

        await self.ensure_command_ready(session)
        workspace = session.workspace or self.workspace_path
        if not Path(workspace).exists():
            raise WorkspaceNotFoundError("工作目录不存在。")

        async with session.lock:
            session.thread_id = None
            session.status = "stopped"
            session.status_detail = "已就绪，等待指令"
        await self.transport.broadcast(
            {"type": "session_started", "session": session.serialize()}
        )
        await self._broadcast_state()
        return session

    async def stop_session(self, session_id: str) -> SessionRecord:
        session = self._get_session(session_id)
        async with session.lock:
            if session.active_process and session.active_process.returncode is None:
                session.active_process.terminate()
                try:
                    await asyncio.wait_for(session.active_process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    session.active_process.kill()
            session.active_process = None
            session.thread_id = None
            session.status = "stopped"
            session.status_detail = "已停止，发送新指令将开启新的会话"
            message = session.append_system("已停止 Codex 会话。")
        await self.transport.broadcast_messages(session.id, [message])
        await self.transport.broadcast(
            {"type": "session_stopped", "session": session.serialize()}
        )
        await self._broadcast_state()
        return session

    async def delete_session(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if not session:
            raise SessionNotFoundError()
        if session.active_process and session.active_process.returncode is None:
            await self.stop_session(session_id)
        self.sessions.pop(session_id, None)
        await self._broadcast_state()

    async def send_input(self, session_id: str, text: str, forwarded_by: Optional[str]) -> SessionRecord:
        session = self._get_session(session_id)
        normalized = text.rstrip("\n")
        if not normalized:
            raise InvalidSessionInputError("输入不能为空")
        if session.active_process and session.active_process.returncode is None:
            raise SessionConflictError("Codex 正在处理上一条指令")
        message = ChatMessage(
            id=str(uuid.uuid4()),
            role="user",
            timestamp=self.now_iso(),
            parts=[MessagePart(text=f"{normalized}\n")],
            forwarded_by=forwarded_by,
            origin_session=forwarded_by,
            kind="input",
        )
        session.append_message(message)
        await self.transport.broadcast_messages(session.id, [message])
        await self._broadcast_state()
        await self._run_exec(session, normalized)
        return session

    async def clear_session(self, session_id: str) -> SessionRecord:
        session = self._get_session(session_id)
        session.messages.clear()
        await self._broadcast_state()
        return session

    async def save_session(self, session_id: str) -> Path:
        session = self._get_session(session_id)
        if not session.messages:
            raise InvalidSessionInputError("没有可保存的消息")
        now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        directory = Path("chat_logs") / session.role.get("name", "session")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"chat_{now}.md"
        with path.open("w", encoding="utf-8") as file:
            file.write(f"# Codex 会话日志 — {session.role.get('name', '角色')}\n\n")
            file.write(f"命令：{session.command}\n")
            file.write(f"工作目录：{session.workspace}\n\n")
            for message in session.messages:
                label = {
                    "user": "用户",
                    "codex": "Codex",
                    "system": "系统",
                }.get(message.role, message.role)
                forwarded = (
                    f"（由 {message.forwarded_by} 转发）"
                    if message.forwarded_by
                    else ""
                )
                file.write(f"## {label}{forwarded} ({message.timestamp})\n\n````text\n")
                for part in message.parts:
                    if part.is_error:
                        file.write("[stderr]\n")
                    file.write(part.text)
                file.write("````\n\n")
        message = session.append_system(f"已保存日志到 {path}")
        await self.transport.broadcast_messages(session.id, [message])
        await self._broadcast_state()
        return path

    # ------------------------------------------------------------------ #
    # Configuration
    # ------------------------------------------------------------------ #
    async def update_workspace(self, path: str) -> None:
        resolved = str(Path(path).expanduser().resolve())
        self._workspace_path = resolved
        self._resolved_path_env = None
        await self._broadcast_state()

    async def apply_config(self, payload: Dict[str, Optional[str]]) -> None:
        updates = {key: value for key, value in payload.items() if value is not None}
        if "command" in updates:
            value = (updates["command"] or "").strip()
            if not value:
                raise InvalidSessionInputError("命令不能为空")
            self.global_config["command"] = value
        if "args" in updates:
            self.global_config["args"] = updates["args"] or ""
        if "workspace" in updates:
            workspace = updates["workspace"] or ""
            if workspace:
                resolved = str(Path(workspace).expanduser().resolve())
                self.global_config["workspace"] = resolved
                self._workspace_path = resolved
                self._resolved_path_env = None
        for key in ("model", "reasoning", "summary", "approval", "sandbox"):
            if key in updates:
                self.global_config[key] = updates[key] or self.global_config[key]
        for session in self.sessions.values():
            session.command = self.global_config["command"]
            session.args = self.global_config["args"]
            session.workspace = self.global_config["workspace"]
            session.model = self.global_config["model"]
            session.reasoning = self.global_config["reasoning"]
            session.summary = self.global_config["summary"]
            session.approval = self.global_config["approval"]
            session.sandbox = self.global_config["sandbox"]
        await self._broadcast_state()

    async def select_directory(self) -> str:
        loop = asyncio.get_running_loop()
        initial = self.global_config.get("workspace", self.workspace_path)

        def choose_with_tk(initial_dir: str) -> str:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                path = filedialog.askdirectory(initialdir=initial_dir or os.getcwd())
            finally:
                root.destroy()
            return path or ""

        def choose_with_osascript(initial_dir: str) -> str:
            escaped = initial_dir.replace("\\", "\\\\").replace('"', '\\"')
            script_parts = [
                f'set defaultFolder to POSIX file "{escaped}"',
                "try",
                'set chosenFolder to choose folder with prompt "选择工作目录" default location defaultFolder',
                "on error number -128",
                'return ""',
                "end try",
                "POSIX path of chosenFolder",
            ]
            cmd: List[str] = ["osascript"]
            for part in script_parts:
                cmd.extend(["-e", part])
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:
                return ""
            if result.returncode != 0:
                return ""
            return result.stdout.strip()

        try:
            result = await loop.run_in_executor(None, choose_with_tk, initial)
            if result:
                return result
        except ModuleNotFoundError:
            pass
        except Exception:
            pass

        if sys.platform == "darwin":
            result = await loop.run_in_executor(None, choose_with_osascript, initial)
            if result:
                return result

        raise InvalidSessionInputError(
            "未选择目录，或当前环境缺少可用的目录选择器（建议安装 Tk 或使用 macOS AppleScript）。"
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _get_session(self, session_id: str) -> SessionRecord:
        session = self.sessions.get(session_id)
        if not session:
            raise SessionNotFoundError()
        return session

    async def ensure_command_ready(self, session: SessionRecord) -> None:
        command = session.command.strip()
        if not command:
            raise CommandUnavailableError("命令不能为空。")
        path_env = await self.resolve_path_env()
        if os.path.sep in command:
            candidate = Path(command)
            if candidate.exists() and os.access(candidate, os.X_OK):
                return
        if shutil.which(command, path=path_env):
            return
        raise CommandUnavailableError(
            f'未找到命令 "{command}"，请确认已安装 Codex CLI 或在命令栏填入绝对路径。'
        )

    async def resolve_path_env(self) -> str:
        if self._resolved_path_env:
            return self._resolved_path_env
        path_values: set[str] = set()
        env_path = os.environ.get("PATH")
        if env_path:
            path_values.update(env_path.split(os.pathsep))
        path_values.update(
            {
                "/usr/local/bin",
                "/opt/homebrew/bin",
                "/usr/bin",
                "/bin",
                str(Path(self.workspace_path)),
            }
        )
        if os.name == "posix" and shutil.which("zsh"):
            try:
                result = await asyncio.create_subprocess_exec(
                    "zsh",
                    "-lc",
                    'print -r -- "$PATH"',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await result.communicate()
                if stdout:
                    path_values.update(stdout.decode().strip().split(":"))
            except Exception:
                pass
        self._resolved_path_env = os.pathsep.join(sorted(filter(None, path_values)))
        return self._resolved_path_env

    async def _run_exec(self, session: SessionRecord, prompt: str) -> None:
        env = {**os.environ, "PATH": await self.resolve_path_env()}
        config = CodexExecConfig(
            command=session.command,
            args=tuple(shlex.split(session.args)) if session.args else tuple(),
            workspace=session.workspace or self.workspace_path,
            model=session.model,
            reasoning_effort=session.reasoning,
            summary_style=session.summary,
            approval_policy=session.approval,
            sandbox=session.sandbox,
        )
        async with session.lock:
            if session.active_process and session.active_process.returncode is None:
                raise SessionConflictError("Codex 正在处理上一条指令")
            session.status = "running"
            session.status_detail = "Codex 处理中…"
        await self._broadcast_state()

        process_holder: List[Process] = []

        async def emit(event: SessionEvent) -> None:
            await self._handle_session_event(event)

        adapter = ManualSessionEventAdapter(session, emit, process_holder)
        dispatcher = adapter.build_dispatcher()

        try:
            await consume_events(
                config,
                prompt=prompt,
                dispatcher=dispatcher,
                resume_session=session.thread_id,
                env=env,
                process_ref=process_holder,
            )
        finally:
            async with session.lock:
                session.active_process = None
                if session.status == "running":
                    session.status = "stopped"
                    session.status_detail = None
            await self._broadcast_state()

    async def _handle_session_event(self, event: SessionEvent) -> None:
        if isinstance(event, SessionMessageEvent):
            await self.transport.broadcast_messages(event.session_id, [event.message])
        elif isinstance(event, SessionTokenEvent):
            await self.transport.broadcast_token_usage(event.session_id, event.usage)
        elif isinstance(event, SessionLifecycleEvent):
            await self._broadcast_state()

    async def _broadcast_state(self) -> None:
        async with self._broadcast_state_lock:
            await self.transport.broadcast_state(self.serialize())


__all__ = ["ManualSessionManager"]
