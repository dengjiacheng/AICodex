from __future__ import annotations

from fastapi import HTTPException, status


class ManualSessionError(RuntimeError):
    """Base exception for manual session domain."""

    message: str = "手动会话发生未知错误"
    http_status: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message

    def to_http_exception(self) -> HTTPException:
        return HTTPException(status_code=self.http_status, detail=self.message)


class SessionNotFoundError(ManualSessionError):
    message = "会话不存在"
    http_status = status.HTTP_404_NOT_FOUND


class SessionConflictError(ManualSessionError):
    message = "当前会话正在处理请求"
    http_status = status.HTTP_409_CONFLICT


class InvalidSessionInputError(ManualSessionError):
    message = "输入内容无效"
    http_status = status.HTTP_400_BAD_REQUEST


class CommandUnavailableError(ManualSessionError):
    message = "Codex 命令不可用"
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


class WorkspaceNotFoundError(ManualSessionError):
    message = "工作目录不存在"
    http_status = status.HTTP_400_BAD_REQUEST
