import enum
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    NEEDS_CLARIFICATION = "needs_clarification"


class HandoffSignal(str, enum.Enum):
    CONTINUE = "CONTINUE"
    STOP = "STOP"


@dataclass
class TaskStep:
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "TaskStep":
        return TaskStep(
            id=str(data.get("id") or ""),
            description=str(data.get("description") or ""),
            status=TaskStatus(data.get("status", TaskStatus.PENDING.value)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
        }


@dataclass
class TaskHandoff:
    next_hint: str = ""
    signal: HandoffSignal = HandoffSignal.CONTINUE

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "TaskHandoff":
        signal = data.get("signal") or HandoffSignal.CONTINUE.value
        return TaskHandoff(
            next_hint=str(data.get("next_hint") or ""),
            signal=HandoffSignal(signal),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "next_hint": self.next_hint,
            "signal": self.signal.value,
        }


@dataclass
class CurrentTask:
    id: str
    parent_id: Optional[str]
    title: str
    objective: str
    context_refs: List[str] = field(default_factory=list)
    plan: List[TaskStep] = field(default_factory=list)
    workdir: str = "."
    tests_required: List[str] = field(default_factory=list)
    review_checks: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    handoff: TaskHandoff = field(default_factory=TaskHandoff)
    updated_at: Optional[datetime] = None

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CurrentTask":
        updated_at_value = data.get("updated_at")
        updated_at = None
        if updated_at_value:
            try:
                updated_at = datetime.fromisoformat(updated_at_value)
            except ValueError:
                updated_at = None
        plan_payload = data.get("plan") or []
        plan = [TaskStep.from_dict(item) for item in plan_payload]
        return CurrentTask(
            id=str(data.get("id") or ""),
            parent_id=data.get("parent_id"),
            title=str(data.get("title") or ""),
            objective=str(data.get("objective") or ""),
            context_refs=list(data.get("context_refs") or []),
            plan=plan,
            workdir=str(data.get("workdir") or "."),
            tests_required=list(data.get("tests_required") or []),
            review_checks=list(data.get("review_checks") or []),
            status=TaskStatus(data.get("status", TaskStatus.PENDING.value)),
            handoff=TaskHandoff.from_dict(data.get("handoff") or {}),
            updated_at=updated_at,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "title": self.title,
            "objective": self.objective,
            "context_refs": list(self.context_refs),
            "plan": [step.to_dict() for step in self.plan],
            "workdir": self.workdir,
            "tests_required": list(self.tests_required),
            "review_checks": list(self.review_checks),
            "status": self.status.value,
            "handoff": self.handoff.to_dict(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def located_workdir(self, root: Path) -> Path:
        candidate = (root / self.workdir).resolve()
        return candidate


@dataclass
class AutoTaskState:
    status: str = "idle"
    current_task: Optional[CurrentTask] = None
    thread_id: Optional[str] = None
    attempts: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "current_task": self.current_task.to_dict() if self.current_task else None,
            "thread_id": self.thread_id,
            "attempts": self.attempts,
            "last_error": self.last_error,
        }
