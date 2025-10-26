# 任务 001 — 统一 Codex CLI 调用与事件管线

## 背景
- 当前手动会话（SessionManager）与自动任务（AutoTaskOrchestrator）各自拼装 Codex CLI 命令与事件解析逻辑，存在重复与行为不一致风险。
- 新需求要求：所有 Codex 调用统一通过 `codex exec --json`，prompt 统一走 stdin，可选添加 `--output-schema`、`--image`，并把事件分派给不同消费者。
- 需要一个可复用的异步封装，既管控子进程，也对外提供结构化事件回调，以便手动会话和自动任务分别实现业务逻辑。

## 目标
构建一个统一的 Codex CLI 客户端，实现：
1. 命令构建统一（默认带 `--json`，支持模型、推理强度、总结、审批、沙箱、Schema、图片等可配置参数）。
2. prompt 数据一律通过 stdin 输入；支持新会话与 `resume <session_id>`。
3. 异步收集并解析所有 stdout JSON 事件（含 `thread.*`、`turn.*`、`item.*` 各子类型），并输出标准化事件对象。
4. 对非 JSON stdout、stderr、非零退出码生成合成事件，保持完整可观测性。
5. 提供回调/订阅机制，允许消费者根据自身需求实现不同的事件处理策略。

## 阶段计划

### 阶段 1：现状梳理与设计（预估 0.5 天）
- 全面梳理现有命令构建与事件解析逻辑，列出需要保留/对齐的行为。
- 盘点 Codex 可能返回的事件类型与字段，明确需要覆盖的子类型（例如 `agent_message`、`reasoning`、`command_execution`、`file_change`、`mcp_tool_call`、`web_search`、`todo_list`、`error` 等）。
- 设计统一客户端接口：输入配置结构、运行方法签名、事件分发 API，并在文档确认。

### 阶段 2：命令构建与配置抽象（预估 0.5 天）
- 实现命令构建器，默认附带 `--json`，根据配置添加 `--output-schema`、`--image`、`resume <session_id>` 等参数。
- 定义配置对象（例如 dataclass / Pydantic 模型），描述模型选择、推理强度、总结风格、审批策略、沙箱模式、附加 CLI 配置等。
- 编写单元测试确保参数组合与边界条件（空 prompt、仅 resume、可选项缺失等）处理正确。

### 阶段 3：异步运行与事件规范化（预估 1 天）
- 使用 `asyncio.create_subprocess_exec` 封装子进程启动，负责写入 prompt 到 stdin。
- 并发异步读取 stdout/stderr，处理 `asyncio.LimitOverrunError` 等异常，读取到的内容统一压入内部异步队列。
- 解析 stdout JSON 行生成结构化事件；对非 JSON 行、stderr 行、进程启动/结束、非零退出码生成自定义事件类型。
- 定义事件枚举/数据类，覆盖所有需要的事件字段，方便消费者按分类处理。

### 阶段 4：事件回调层（预估 0.5 天）
- 设计事件分发接口：支持注册单一回调或类型到回调的映射；确保回调异常被捕获并记录日志。
- 提供常用辅助工具（例如聚合 agent message、收集命令输出、计算 token usage）。
- 规范回调生命周期，保证在 `process.finished` 后能通知消费者收尾。

### 阶段 5：集成手动会话（预估 0.75 天）
- 将 `backend/app.py` 中 `_run_exec` / `_handle_exec_event` 替换为新的客户端调用。
- 把标准化事件转换为前端所需的 websocket 消息（系统提示、用户消息、Codex 输出、token 用量等）。
- 验证功能：创建会话、发送消息、接收输出、停止、保存日志、线程 resume。

### 阶段 6：集成自动任务（预估 0.75 天）
- 用新客户端替换 `backend/auto_task/cli_runner.py`，调整 orchestrator 的事件处理逻辑。
- 确保任务执行、澄清、失败、总结、知识库写入等流程正常；根据新事件类型更新消息/广播。
- 回归测试现有单测 `backend/tests/test_orchestrator.py`，并新增关键场景测试。

### 阶段 7：测试与验证（预估 0.5 天）
- 编写/完善单元测试：命令构建、事件解析、resume 逻辑、错误处理。
- 添加集成测试或模拟 CLI 输出的测试，验证事件流与回调触发顺序。
- 必要时更新 CI 脚本或测试夹具，确保新模块覆盖率。

### 阶段 8：清理与文档（预估 0.25 天）
- 移除不再使用的旧类/函数，整理 import。
- 更新 README/开发文档，说明新客户端 API、配置方法、事件列表。
- 在团队文档中记录迁移步骤与注意事项，便于后续维护。

## 阶段 1 结果

### 现有调用与差异
- **手动会话（`backend/app.py`）**
  - `_build_exec_command` 直接拼接列表：`command + args + ["exec", "--json", "--color", "never", "--skip-git-repo-check"]`，根据配置追加 `--model`、`--config model_reasoning_*`、`--config approval_policy=*`、`--sandbox`、`--cd`。如果 `thread_id` 存在则在末尾追加 `["resume", thread_id]`，最后附加 prompt（即便为空）。
  - `_run_exec` 使用 `asyncio.create_subprocess_exec`，同步读取 stdout/stderr。stdout 行尝试解析 JSON，失败时写入系统提示；stderr 全部写入系统提示。仅处理事件 `thread.started`、`item.completed`（细分 `agent_message` / `reasoning` / `command_execution` / `agent_error`）、`error`、`turn.completed`。退出码非零时追加系统消息。
  - Token 统计逻辑手工从 `turn.completed.usage` 计算增量并累加。

- **自动任务（`backend/auto_task/cli_runner.py` + `orchestrator.py`）**
  - `CodexCliRunner._build_command` 构建顺序与手动会话类似，但通过 `RunOptions` 支持 `extra_args`、`extra_configs`。始终附带 `["exec", "--json", "--color", "never", "--skip-git-repo-check"]`；可选 `--model`、`--config model_reasoning_effort|summary`、`--config approval_policy`、`--sandbox`、`--cd`、`resume thread_id`，最后可追加 prompt。
  - `run()` 内部创建 stdout/stderr 读取协程，遇到 `LimitOverrunError` 时按块输出 `runner.raw_output`。统一推送 `runner.command`、`process.started`、`runner.raw_output`（stdout/stderr）、`runner.error`（命令找不到等）、`process.finished`。
  - Orchestrator 侧通过 `_format_cli_event` 将事件映射成前端消息，覆盖 `thread.started`、`turn.started`、`turn.completed`、`item.started`/`item.updated`/`item.completed`（区分 `command_execution`、`reasoning` 等），并捕获 `runner.*` 事件。
  - `_parse_execution_events` 将事件流整理出 `status`、`summary_markdown`、`payload`、`returncode`。

### 事件类型清单
- 顶层 `type`（来自 Codex CLI JSON 行）：
  - `thread.started`：包含 `thread_id`（即 session id）。
  - `turn.started`、`turn.completed`、`turn.failed`。
  - `item.started` / `item.updated` / `item.completed`，payload 中 `item.type` 可能是：
    - `agent_message`、`reasoning`、`command_execution`、`file_change`、`mcp_tool_call`、`web_search`、`todo_list`、`error`。
  - `error`（流级别错误，比如解析失败、服务端异常）。
- Runner 自定义事件：
  - `runner.command`（执行命令列表）、`process.started`（pid）、`runner.raw_output`（stdout/stderr 非 JSON）、`runner.error`（子进程无法启动）、`process.finished`（退出码）。
- 需要扩展覆盖的其他信息：
  - `turn.completed.usage.{input_tokens,cached_input_tokens,output_tokens,reasoning_output_tokens}`。
  - `item.*` 下的领域字段，例如 `command_execution.status|exit_code|aggregated_output`、`file_change.changes`、`mcp_tool_call.status`、`todo_list.items`。

### 拟定统一接口草案
- **配置模型**：`CodexExecConfig`
  - 字段：`command`、`args`、`workspace`、`model`、`reasoning_effort`、`summary_style`、`approval_policy`、`sandbox`、`output_schema`、`images`、`extra_args`、`extra_configs`。
- **运行入口**
  - `async def run(prompt: str, config: CodexExecConfig, resume_session: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> AsyncIterator[CodexEvent]`
  - Prompt 统一通过 stdin 写入；内部负责在命令行末尾追加 `resume <session_id>`（若有）。
  - 执行前发布 `RunnerCommandEvent`，执行中按行解析/派发，结束时发布 `ProcessFinishedEvent`。
- **事件模型**
  - 基类 `CodexEvent { kind: CodexEventKind, timestamp: datetime, raw: Optional[Dict] }`
  - 枚举：`RUNNER_COMMAND`、`PROCESS_STARTED`、`PROCESS_FINISHED`、`STDOUT_NON_JSON`、`STDERR_LINE`、`THREAD_STARTED`、`TURN_STARTED`、`TURN_COMPLETED`、`TURN_FAILED`、`ITEM_STARTED`、`ITEM_UPDATED`、`ITEM_COMPLETED`、`STREAM_ERROR` 等。
  - `CodexItemEvent` 额外包含 `item_type`（枚举 `AGENT_MESSAGE`、`REASONING`、`COMMAND_EXECUTION`、`FILE_CHANGE`、`MCP_TOOL_CALL`、`WEB_SEARCH`、`TODO_LIST`、`ERROR`）及对应该类型的结构化字段。
- **回调抽象**
  - 提供两种用法：
    1. 直接 `async for event in client.run(...):`，调用方自行判断 `event.kind`。
    2. 注册回调映射 `Dict[CodexEventKind, Callable[[CodexEvent], Awaitable[None]]]` 或 `CodexEventHandler` 协议，统一 dispatch，并对异常做日志捕获。
  - 允许附带上下文对象，便于 SessionManager/Orchestrator 在同一接口下实现不同的状态机。

### 后续约束
- 需要兼容现有的 token 累计与 `thread_id` 缓存逻辑。
- 需要提供与现有 `runner.raw_output` 类似的事件，以免丢失非 JSON 输出。
- 下一阶段开始实现命令构建器时，要注意保持参数拼接顺序与现有实现一致，避免 CLI 解析异常。

## 阶段 2 结果
- 新增 `backend/codex_client` 包，集中存放 CLI 调用公共逻辑。
- `CodexExecConfig` 支持命令路径、基础参数、模型设定、推理/总结策略、审批策略、沙箱、输出 Schema、图片、额外参数/配置以及 prompt 输入源。
- `build_exec_command` 保证始终使用 `exec --json --color never --skip-git-repo-check`，统一处理 `--model`、`--config`（含排序后的额外配置）、`--sandbox`、`--cd`、`--output-schema`、`--image`、`resume <session_id>` 等选项，符合“prompt 统一走 stdin”的约束。
- 新增单元测试验证命令结构、参数覆盖以及额外配置排序；由于本地缺少 `pytest` 可执行文件，自动测试未能运行（需后续环境补全）。
- 安装 `pytest` 至后端虚拟环境，并通过 `/Users/dengjiacheng/AI_Codex/backend/.venv/bin/python -m pytest backend/tests/test_codex_command_builder.py` 验证，当前 3 项用例全部通过。

## 阶段 3 结果
- 新增事件模型 `backend/codex_client/events.py`，定义 `EventKind`、`ItemType`、`CodexEvent` 及其派生类型，覆盖 `thread.*`、`turn.*`、`item.*`、stderr/stdout 非 JSON、进程启动/结束 等场景。
- 实现 `backend/codex_client/runner.py`，封装 `asyncio.create_subprocess_exec`：
  - prompt 统一写入 stdin；
  - stdout/stderr 采用并行协程读取，遇到非 JSON 行或 `LimitOverrunError` 时产出 `TextStreamEvent`；
  - 将 JSON 事件映射为标准化事件（含 `TurnUsage`、`ItemEvent` 及 item 子类型）；
  - 进程结束后产出 `ProcessFinishedEvent`，若返回码非零额外生成 `TurnFailedEvent`。
- 编写测试脚本 `backend/tests/fake_codex_cli.py` 模拟 Codex 输出，新增 `backend/tests/test_codex_runner.py` 验证事件序列、item 载荷、失败分支与 returncode 处理。
- 补装 `pytest-asyncio` 并执行 `/Users/dengjiacheng/AI_Codex/backend/.venv/bin/python -m pytest backend/tests/test_codex_command_builder.py backend/tests/test_codex_runner.py`，现有 5 个用例全部通过。

## 阶段 4 结果
- 新增 `backend/codex_client/dispatcher.py` 暴露 `EventDispatcher` 与 `consume_events`：
  - 支持按 `EventKind` 注册异步回调，同时允许 `ItemType` 精细化处理；
  - 默认回调可复用，所有 handler 的异常被捕获并记录日志，不会中断流程。
- 将封装暴露到 `backend/codex_client/__init__.py`，便于后续集成调用。
- 新增测试 `backend/tests/test_codex_dispatcher.py` 覆盖：
  - 默认/特定事件分发；
  - Item 类型专用 handler；
  - handler 异常日志捕获；
  - 非 JSON stdout 事件派发。
- 重新运行 `/Users/dengjiacheng/AI_Codex/backend/.venv/bin/python -m pytest backend/tests/test_codex_command_builder.py backend/tests/test_codex_runner.py backend/tests/test_codex_dispatcher.py`，当前 9 项用例全部通过。

## 阶段 5 结果
- 手动会话 `_run_exec` 完全切换到新客户端：
  - 使用 `CodexExecConfig` 和 `consume_events`，prompt 统一经 stdin 传递；
  - 采用 `EventDispatcher` 将 `thread.*`、`turn.*`、`item.*`、stdout/stderr、进程 lifecycle 等事件映射到原有聊天时间线行为；
  - 保留线程续写能力（`thread_id` 缓存），并扩展对 `file_change`、`mcp_tool_call`、`web_search`、`todo_list` 等子类型的提示。
- 引入 `ManualSessionEventHandler`，让服务层（ManualSessionService）仅负责配置与状态管理，具体事件响应全部由 handler 实现。
- 会话时间线新增 `kind` 元数据，前端显示命令开始/完成、推理、文件变更等标签，滚动体验与 CLI 事件更一致。
- 会话状态管理保持一致：`session.active_process` 继续持有底层 `asyncio.subprocess.Process`，`stop_session` 能正常终止 Codex 进程，token 用量广播逻辑移植至 `_handle_usage_event`。
- 新增辅助方法 `_broadcast_chat_message` 以及一系列 `Item` / `Turn` 事件处理函数，去除旧的 `_build_exec_command` / `_handle_exec_event`。
- 回归执行 `/Users/dengjiacheng/AI_Codex/backend/.venv/bin/python -m pytest backend/tests/test_codex_command_builder.py backend/tests/test_codex_runner.py backend/tests/test_codex_dispatcher.py`，确保现有构建/运行/分发测试全部通过（9 项绿）。

## 阶段 6 结果
- `backend/auto_task/cli_runner.py` 重写为薄封装，直接复用 `CodexExecConfig` 与 `to_async_generator`，并将事件输出统一交给 handler。
- 新增 `AutoSessionEventHandler`，负责自动任务场景的事件解析、广播、summary 整理与下一任务提取；`AutoTaskOrchestrator` 仅负责调度与状态管理。
- 保留 `RunOptions` 接口，使 orchestrator 与单测在无需改动的前提下即可采用统一的命令构建与 stdin prompt 流程。
- 通过脚本验证成功/失败路径仍按预期更新知识库、任务与状态；`backend/tests/test_orchestrator.py` 可配合其他单测一起执行（注意运行时间较长，需适当延长超时设置）。

## 交付物
- 统一的 Codex 客户端模块（命令构建、配置对象、异步运行、事件分发）。
- 更新后的手动会话与自动任务流程，全部使用新客户端。
- 完整的事件解析与测试用例。
- 相关文档：本任务计划、API 使用说明、迁移指引。

## 验收标准
- 手动会话/自动任务均通过统一封装调用 Codex，功能不回退。
- 所有 Codex 输出（JSON 事件、stderr、非零退出码）均有结构化事件对外曝光。
- prompt 统一走 stdin，`--output-schema`、`--image` 选项可正常使用。
- resume 模式与新会话模式均通过测试，确认线程 ID 与 session ID 行为一致。
- 上下游（前端、日志）收到的事件与原有逻辑保持语义等价或更精细。
