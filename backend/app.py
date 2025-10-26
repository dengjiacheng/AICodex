from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.auto_task.cli_runner import CodexCliRunner
from backend.auto_task.orchestrator import AutoTaskOrchestrator
from backend.auto_task.router import router as auto_task_router
from backend.auto_task.storage import AutoTaskStorage
from backend.manual_session import (
    AppState,
    ConfigPayload,
    ManualSessionService,
    MessagePayload,
    SessionCreate,
    SessionUpdate,
    WorkspacePayload,
)

APP_TITLE = "Codex Multi-Role Gateway"

logging.basicConfig(level=logging.INFO)

auto_task_storage = AutoTaskStorage(Path.cwd())
auto_task_runner = CodexCliRunner()
auto_task_orchestrator = AutoTaskOrchestrator(
    auto_task_storage,
    auto_task_runner,
)

manual_session_service = ManualSessionService()
auto_task_orchestrator.set_config_provider(manual_session_service.get_auto_task_config)

app = FastAPI(title=APP_TITLE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auto_task_router, prefix="/auto-task", tags=["auto-task"])


@app.on_event("startup")
async def _startup_auto_task() -> None:
    await auto_task_storage.ensure_structure()
    app.state.auto_task_storage = auto_task_storage
    app.state.auto_task_orchestrator = auto_task_orchestrator
    app.state.session_service = manual_session_service
    app.state.session_manager = manual_session_service.manager


@app.get("/state", response_model=AppState)
async def get_state() -> AppState:
    return manual_session_service.serialize()


@app.post("/workspace")
async def update_workspace(payload: WorkspacePayload) -> Dict[str, str]:
    await manual_session_service.update_workspace(payload.path)
    return {"status": "ok"}


@app.post("/sessions")
async def create_session(payload: SessionCreate) -> Dict[str, object]:
    session = await manual_session_service.create_session(
        payload.model_dump(exclude_none=True)
    )
    return {"session": session.serialize()}


@app.patch("/sessions/{session_id}")
async def update_session(
    session_id: str, payload: SessionUpdate
) -> Dict[str, object]:
    session = await manual_session_service.update_session(
        session_id, payload.model_dump(exclude_none=True)
    )
    return {"session": session.serialize()}


@app.post("/sessions/{session_id}/start")
async def start_session(session_id: str) -> Dict[str, object]:
    session = await manual_session_service.start_session(session_id)
    return {"session": session.serialize()}


@app.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str) -> Dict[str, object]:
    session = await manual_session_service.stop_session(session_id)
    return {"session": session.serialize()}


@app.post("/sessions/{session_id}/input")
async def send_input(session_id: str, payload: MessagePayload) -> Dict[str, object]:
    session = await manual_session_service.send_input(
        session_id, payload.text, payload.forwarded_by
    )
    return {"session": session.serialize()}


@app.post("/sessions/{session_id}/clear")
async def clear_session(session_id: str) -> Dict[str, object]:
    session = await manual_session_service.clear_session(session_id)
    return {"session": session.serialize()}


@app.post("/sessions/{session_id}/save")
async def save_session(session_id: str) -> Dict[str, str]:
    path = await manual_session_service.save_session(session_id)
    return {"path": path}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict[str, str]:
    await manual_session_service.delete_session(session_id)
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    transport = manual_session_service.transport
    await transport.register(websocket)
    await transport.send_initial_state(websocket, manual_session_service.serialize())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        transport.unregister(websocket)


@app.post("/config")
async def update_config(payload: ConfigPayload) -> Dict[str, str]:
    await manual_session_service.apply_config(payload.model_dump(exclude_none=True))
    return {"status": "ok"}


@app.post("/select-directory")
async def select_directory() -> Dict[str, str]:
    path = await manual_session_service.select_directory()
    await manual_session_service.apply_config({"workspace": path})
    return {"path": path}


def run() -> None:
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=9000, reload=True)


__all__ = ["app", "run"]
