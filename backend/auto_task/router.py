import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .orchestrator import AutoTaskOrchestrator
from .storage import AutoTaskStorage


router = APIRouter()


class ClarificationPayload(BaseModel):
    message: str


class BootstrapPayload(BaseModel):
    workspace: Optional[str] = None


def get_orchestrator(
    request: Request = None,
    websocket: WebSocket = None,
) -> AutoTaskOrchestrator:
    scope = request or websocket
    if scope is None:
        raise HTTPException(status_code=500, detail="Auto task orchestrator dependency missing scope")
    orchestrator: AutoTaskOrchestrator | None = getattr(
        scope.app.state, "auto_task_orchestrator", None
    )
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Auto task orchestrator unavailable")
    return orchestrator


def get_storage(
    request: Request = None,
    websocket: WebSocket = None,
) -> AutoTaskStorage:
    scope = request or websocket
    if scope is None:
        raise HTTPException(status_code=500, detail="Auto task storage dependency missing scope")
    storage: AutoTaskStorage | None = getattr(scope.app.state, "auto_task_storage", None)
    if storage is None:
        raise HTTPException(status_code=503, detail="Auto task storage unavailable")
    return storage


@router.get("/state")
async def get_state(orchestrator: AutoTaskOrchestrator = Depends(get_orchestrator)) -> Dict[str, Any]:
    return orchestrator.get_state()


@router.post("/start")
async def start(orchestrator: AutoTaskOrchestrator = Depends(get_orchestrator)) -> Dict[str, str]:
    try:
        await orchestrator.start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "running"}


@router.post("/stop")
async def stop(orchestrator: AutoTaskOrchestrator = Depends(get_orchestrator)) -> Dict[str, str]:
    try:
        await orchestrator.stop()
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "paused"}


@router.post("/ack")
async def acknowledge(
    payload: ClarificationPayload,
    orchestrator: AutoTaskOrchestrator = Depends(get_orchestrator),
) -> Dict[str, str]:
    await orchestrator.submit_user_clarification(payload.message)
    return {"status": "received"}


@router.post("/bootstrap")
async def bootstrap(
    payload: BootstrapPayload,
    request: Request,
    storage: AutoTaskStorage = Depends(get_storage),
) -> Dict[str, str]:
    workspace = payload.workspace.strip() if payload.workspace else None
    if not workspace:
        manager = getattr(request.app.state, "session_manager", None)
        workspace = getattr(manager, "workspace_path", None)
    target = Path(workspace).expanduser() if workspace else storage.project_root
    try:
        codex_path = storage.bootstrap_workspace(target)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "codex_path": str(codex_path)}


@router.websocket("/ws")
async def auto_task_ws(
    websocket: WebSocket,
    orchestrator: AutoTaskOrchestrator = Depends(get_orchestrator),
) -> None:
    await websocket.accept()
    queue = await orchestrator.register_listener()

    async def producer() -> None:
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            orchestrator.unregister_listener(queue)

    async def consumer() -> None:
        try:
            while True:
                message = await websocket.receive_text()
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "clarification" and "text" in payload:
                    await orchestrator.submit_user_clarification(str(payload["text"]))
        except WebSocketDisconnect:
            pass

    sender = asyncio.create_task(producer())
    receiver = asyncio.create_task(consumer())
    done, pending = await asyncio.wait(
        {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*done, return_exceptions=True)
    await asyncio.gather(*pending, return_exceptions=True)


@router.get("/tasks/{task_id}")
async def get_task_summary(
    task_id: str,
    storage: AutoTaskStorage = Depends(get_storage),
) -> Dict[str, Any]:
    archive_dir = storage.codex_root / "tasks" / "archive"
    summary_path = archive_dir / f"{task_id}.md"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Task summary not found")
    content = summary_path.read_text(encoding="utf-8")
    return {"task_id": task_id, "summary": content}
