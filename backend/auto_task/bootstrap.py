from __future__ import annotations

from pathlib import Path
from textwrap import dedent


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_SOURCE_DIR = REPO_ROOT / ".codex" / "prompts"


def _load_prompt(name: str) -> str:
    source = PROMPT_SOURCE_DIR / f"{name}.md"
    if source.exists():
        return source.read_text(encoding="utf-8")
    return ""


DIRECTORIES = [
    ".codex",
    ".codex/knowledge",
    ".codex/knowledge/modules",
    ".codex/knowledge/apis",
    ".codex/knowledge/tasks",
    ".codex/knowledge/diffs",
    ".codex/tasks",
    ".codex/tasks/archive",
    ".codex/history",
    ".codex/history/sessions",
    ".codex/history/alerts",
    ".codex/history/metrics",
    ".codex/prompts",
]

TEMPLATES = {
    ".codex/README.md": dedent(
        """
        # `.codex/` 目录说明

        自动任务系统相关的知识库、任务元数据、日志与 Prompt 模板均集中存放在此目录。
        代码、测试、部署脚本仍位于项目正常结构中。

        - `knowledge/`：项目概要、模块说明、API 列表等。
        - `tasks/`：`current.json` 是当前任务描述，`archive/` 保存历史小结。
        - `history/`：会话事件、警报与统计。
        - `prompts/`：自动任务使用的 Prompt 模板。
        """
    ).strip()
    + "\n",
    ".codex/knowledge/overview.md": dedent(
        """
        # 项目概览（占位）

        首次运行 bootstrap 会话后，请替换此内容为真实项目背景。
        """
    ).strip()
    + "\n",
    ".codex/knowledge/roadmap.md": dedent(
        """
        # 项目路线图（占位）

        | 阶段 | 目标 | 预计完成 | 备注 |
        | ---- | ---- | -------- | ---- |
        | TODO | 待填写 | - | - |
        """
    ).strip()
    + "\n",
    ".codex/knowledge/tasks/completed_index.json": "[]\n",
    ".codex/tasks/current.json": dedent(
        """
        {
          "id": "INIT",
          "parent_id": null,
          "title": "等待自动化初始化",
          "objective": "运行 bootstrap_context 提示词，收集项目背景并生成首个可执行任务。",
          "context_refs": [],
          "plan": [],
          "workdir": ".",
          "tests_required": [],
          "review_checks": [],
          "status": "pending",
          "handoff": {
            "next_hint": "引导完成后调用 task_planner 替换此占位任务。",
            "signal": "CONTINUE"
          },
          "updated_at": null
        }
        """
    ).strip()
    + "\n",
    ".codex/auto_task_requirements.md": dedent(
        """
        # 自动任务系统需求（占位）

        请在此填写项目的自动任务需求、数据结构与异常策略。
        """
    ).strip()
    + "\n",
    ".codex/auto_task_design.md": dedent(
        """
        # 自动任务架构设计（占位）

        在详细设计完成前，此文件保留概要说明。
        """
    ).strip()
    + "\n",
    ".codex/prompts/README.md": dedent(
        """
        # Prompt 模板目录

        - `bootstrap_context.md`
        - `task_executor.md`
        - `knowledge_curator.md`
        - `task_planner.md`
        - `exception_handler.md`

        初次初始化时可先放置占位文件，后续再补充具体模板内容。
        """
    ).strip()
    + "\n",
    ".codex/prompts/bootstrap_context.md": _load_prompt("bootstrap_context"),
    ".codex/prompts/task_executor.md": _load_prompt("task_executor"),
    ".codex/prompts/knowledge_curator.md": _load_prompt("knowledge_curator"),
    ".codex/prompts/task_planner.md": _load_prompt("task_planner"),
    ".codex/prompts/exception_handler.md": _load_prompt("exception_handler"),
}


def bootstrap_codex(root: Path) -> Path:
    """
    Create the `.codex` directory structure and placeholder files under ``root``.

    Existing files will be preserved.
    """

    for directory in DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)
    for relative_path, content in TEMPLATES.items():
        target = root / relative_path
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root / ".codex"
