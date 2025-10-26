from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple


class PromptSource(str, Enum):
    """Where the prompt payload should be read from when invoking Codex."""

    STDIN = "stdin"
    ARGUMENT = "argument"


def _as_tuple(value: Optional[Sequence[str]]) -> Tuple[str, ...]:
    if not value:
        return ()
    return tuple(item for item in value if item)


def _from_args(value: Optional[Sequence[str] | str]) -> Tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return tuple(shlex.split(value))
    return _as_tuple(value)


@dataclass
class CodexExecConfig:
    """
    Shared configuration for Codex CLI `exec --json`.

    This structure is intentionally agnostic to specific callers (manual
    sessions, auto-task orchestrator, etc.) while covering the flags we rely on
    today. The prompt content itself is handled separately by the caller.
    """

    command: str = "codex"
    args: Tuple[str, ...] = field(default_factory=tuple)
    workspace: Optional[str] = None
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    summary_style: Optional[str] = None
    approval_policy: Optional[str] = None
    sandbox: Optional[str] = None
    output_schema: Optional[str] = None
    images: Tuple[str, ...] = field(default_factory=tuple)
    extra_args: Tuple[str, ...] = field(default_factory=tuple)
    extra_configs: Mapping[str, str] = field(default_factory=dict)
    prompt_source: PromptSource = PromptSource.STDIN

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", _from_args(self.args))
        object.__setattr__(self, "images", _as_tuple(self.images))
        object.__setattr__(self, "extra_args", _from_args(self.extra_args))
        # Convert mapping-type extra configs to plain dict to avoid surprises.
        object.__setattr__(self, "extra_configs", dict(self.extra_configs or {}))

    @classmethod
    def from_defaults(
        cls,
        *,
        command: str = "codex",
        args: Optional[Sequence[str] | str] = None,
        workspace: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        summary_style: Optional[str] = None,
        approval_policy: Optional[str] = None,
        sandbox: Optional[str] = None,
    ) -> "CodexExecConfig":
        return cls(
            command=command,
            args=_from_args(args),
            workspace=workspace,
            model=model,
            reasoning_effort=reasoning_effort,
            summary_style=summary_style,
            approval_policy=approval_policy,
            sandbox=sandbox,
        )

    def with_overrides(
        self,
        *,
        args: Optional[Sequence[str] | str] = None,
        workspace: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        summary_style: Optional[str] = None,
        approval_policy: Optional[str] = None,
        sandbox: Optional[str] = None,
        output_schema: Optional[str] = None,
        images: Optional[Sequence[str]] = None,
        extra_args: Optional[Sequence[str] | str] = None,
        extra_configs: Optional[Mapping[str, str]] = None,
        prompt_source: Optional[PromptSource] = None,
    ) -> "CodexExecConfig":
        """
        Return a new configuration with specific fields overridden.
        """

        merged_configs: Dict[str, str] = dict(self.extra_configs)
        if extra_configs:
            merged_configs.update(extra_configs)

        return CodexExecConfig(
            command=self.command,
            args=_from_args(args) or self.args,
            workspace=workspace or self.workspace,
            model=model or self.model,
            reasoning_effort=reasoning_effort or self.reasoning_effort,
            summary_style=summary_style or self.summary_style,
            approval_policy=approval_policy or self.approval_policy,
            sandbox=sandbox or self.sandbox,
            output_schema=output_schema or self.output_schema,
            images=_as_tuple(images) or self.images,
            extra_args=_from_args(extra_args) or self.extra_args,
            extra_configs=merged_configs,
            prompt_source=prompt_source or self.prompt_source,
        )

