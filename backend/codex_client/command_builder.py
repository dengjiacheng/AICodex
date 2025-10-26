from __future__ import annotations

from typing import List, Tuple

from backend.codex_client.config import CodexExecConfig


def build_exec_command(
    config: CodexExecConfig,
    *,
    resume_session: str | None = None,
) -> Tuple[str, ...]:
    """
    Assemble the Codex CLI command for `exec --json`.

    The prompt itself is expected to be provided via stdin by the caller. This
    helper focuses purely on command-line arguments to keep logic consistent
    between different consumers.
    """

    parts: List[str] = [config.command]
    parts.extend(config.args)

    parts.append("exec")
    parts.extend(["--json", "--color", "never", "--skip-git-repo-check"])
    parts.extend(config.extra_args)

    if config.model:
        parts.extend(["--model", config.model])

    if config.reasoning_effort:
        parts.extend(
            ["--config", f'model_reasoning_effort="{config.reasoning_effort}"']
        )

    if config.summary_style:
        parts.extend(
            ["--config", f'model_reasoning_summary="{config.summary_style}"']
        )

    if config.approval_policy:
        parts.extend(
            ["--config", f'approval_policy="{config.approval_policy}"']
        )

    for key in sorted(config.extra_configs.keys()):
        value = config.extra_configs[key]
        parts.extend(["--config", f'{key}="{value}"'])

    if config.sandbox:
        parts.extend(["--sandbox", config.sandbox])

    if config.workspace:
        parts.extend(["--cd", config.workspace])

    if config.output_schema:
        parts.extend(["--output-schema", config.output_schema])

    if config.images:
        # CLI allows comma-delimited values via value_delimiter option.
        parts.extend(["--image", ",".join(config.images)])

    if resume_session:
        parts.extend(["resume", resume_session])

    return tuple(parts)
