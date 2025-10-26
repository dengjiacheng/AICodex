# 任务 002 — 手动会话模块重构计划

## 背景与目标
- **现状**：手动会话逻辑（`ManualSessionService`、`ManualSessionEventHandler` 等）集中在 `backend/app.py` 中，流程混合了会话状态管理、事件适配、WebSocket 广播等职责，导致耦合高、可维护性差。
- **目标**：
  1. 建立清晰的分层：配置/状态管理、事件处理、WebSocket 推送、Codex CLI 调用分离。
  2. 提供统一的异常与响应封装，避免散落的 `HTTPException`/日志调用。
  3. 提升扩展性：便于未来新增消息管道（如通知/审计）、多会话策略或自定义事件适配。

## 总体架构设计
```
backend/manual_session/
  ├── __init__.py
  ├── manager.py           # 会话生命周期 & 状态同步
+ ├── dispatcher.py        # Codex 事件到领域消息的适配器
  ├── models.py            # Pydantic/dataclass 定义（SessionRecord 等）
  ├── transport.py         # WebSocket 广播 & 消息队列抽象
  ├── errors.py            # 自定义异常 + 错误响应策略
  └── service.py           # Facade，供 FastAPI endpoint 调用
```

- `manager.py`：负责 CRUD、锁管理、命令校验、记录消息、发起 Codex 执行，屏蔽底层事件细节。
- `dispatcher.py`：复用/包装 `EventDispatcher`，将 Codex 事件转换为领域事件；输出统一的 `SessionEvent` 对象，供 manager/transport 消费。
- `transport.py`：封装 `broadcast` 与 `broadcast_state`，管理 WebSocket 客户端、粘性消息格式。
- `errors.py`：定义如 `SessionNotFound`, `CommandUnavailable` 等异常，并提供 `to_http_exception()`/统一日志处理。
- `service.py`：FastAPI 视图依赖注入的入口，负责参数校验、异常拦截、调用 manager。

## 实施步骤
1. **模型与异常抽取**
   - 将 `SessionRecord`, `ChatMessage`, `MessagePart`, `ConfigState` 等模型迁移至 `manual_session/models.py`。
   - 新增 `errors.py`，定义核心异常与 `ManualSessionError` 基类。
   - 更新原逻辑以使用新模型模块，保证功能不变。

2. **拆分管理与传输层**
   - 提取 WebSocket 广播相关方法至 `transport.py`（如客户端集合、广播锁、状态序列化）。
   - 在 `manager.py` 中保留业务状态 & Codex 调用；通过注入的 `SessionTransport` 实例进行推送。
   - 确保 `ManualSessionService` 更名/调整为 `ManualSessionManager`，对外暴露最小接口（CRUD、send_input、start/stop 等）。

3. **事件分发器模块化**
   - 将 `ManualSessionEventHandler` 拆到 `dispatcher.py`，输出语义化的 `SessionEvent`（如 `CommandStarted`, `CodexMessageAppended`, `TokenUsageUpdated`）。
   - `manager.py` 订阅这些事件并调用 `transport` 推送，统一处理异常与状态更新。
   - 在此阶段建立统一的错误转换（如 Codex 返回错误 -> `SessionErrorEvent` -> transport 推送）。

4. **服务门面与 FastAPI 集成**
   - 引入 `ManualSessionService`（新）负责组合 `ManualSessionManager`、`SessionTransport`，并暴露给 FastAPI 路由。
   - FastAPI handler 更新引用路径：移除 `backend/app.py` 中的内联类，改为从 `backend.manual_session` 导入。
   - 建立统一异常捕获：service 捕捉 `ManualSessionError`，转换为 `HTTPException`。

5. **清理与回归**
   - 删除 `backend/app.py` 中已迁移的类/方法，仅保留 FastAPI app 定义与路由绑定。
   - 更新现有 `tests`（增加新的单测覆盖 transport/dispatcher 交互、异常路径）。
   - 运行现有测试套件，保证改动不破坏自动任务模块。

## 风险与缓解
- **耦合影响自动任务**：计划保持 auto-task 使用现有接口，不触及 `AutoTaskOrchestrator`。
  - *缓解*：在迁移过程中保留 `manager.get_auto_task_config()` 等接口，并确保导出兼容。
- **广播协议变更风险**：计划初期确保输出 payload 与现有结构兼容，待前端适配后再增量扩展。
  - *缓解*：添加契约测试验证 `message`/`state` 事件结构一致。
- **大型重构回归风险**：拆分为多个提交步骤，并在每阶段运行 `pytest backend/tests`。

## 验收标准
1. `backend/app.py` 仅保留 FastAPI 配置/路由引用；手动会话逻辑迁移到独立模块。
2. 新架构下的 `ManualSessionManager` 提供明确接口，异常统一经 `errors.py` 转换。
3. 运行 `pytest backend/tests` 全部通过；新增单测覆盖事件/错误路径。
4. 文档及类型定义更新，维持前端兼容性。
