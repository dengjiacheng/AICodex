# Codex 多角色 Web 控制台

该项目提供一个基于 **FastAPI + Vue 3** 的「Codex CLI 多角色协作面板」，相比原 Flutter 桌面版更易部署，遵循浏览器/后端分层。

## 目录结构

```
backend/   FastAPI 服务，管理 Codex 进程、多角色状态、消息存档
frontend/  Vue 3 + Vite 前端，提供聊天与配置界面
codex_cli/ 官方 Codex CLI 源码（参考用）
```

## 后端运行

1. 进入 `backend`，创建虚拟环境并安装依赖：
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m ensurepip --upgrade
   python -m pip install -r requirements.txt
   ```
2. 启动服务（默认端口 9000，与前端脚本保持一致）：
   ```bash
   uvicorn backend.app:app --host 0.0.0.0 --port 9000 --reload
   ```

环境变量：
- `CODEX_CMD`：默认 Codex 命令（默认 `codex`）。
- `REPO_ROOT`：默认工作目录（默认当前目录）。

## 前端运行

1. 进入 `frontend`：
   ```bash
   npm install
   npm run dev
   ```
2. 浏览器访问 `http://localhost:5173`。开发代理会将 `/api` 指向 `http://localhost:9000`。

如需自定义接口地址，启动前端前设置 `VITE_API_BASE`，例如：
```bash
VITE_API_BASE=http://127.0.0.1:9000 npm run dev
```

## 功能概览

- 多角色会话管理：支持创建/切换角色以及查看历史记录。
- 参数配置：命令、参数、工作目录与模型等核心选项集中在左侧工具栏调整。
- 消息时间线：实时显示用户/系统/Codex 输出，可折叠并以 Markdown 渲染 Codex 回复。
- WebSocket 推送：前端无需刷新即可感知状态变化。

## 注意事项

- 本项目通过系统 PATH 调用 Codex CLI，如遇返回码 126，请在终端手动运行一次 `codex` 或使用 `xattr -d com.apple.quarantine`、`chmod +x` 授予权限。
- 运行模式默认设为“无需审批 + 完全开放沙箱”，请在受信环境中使用。
- 默认将会话日志输出至 `chat_logs/` 目录，如需纳入版本控制请修改 `.gitignore`。
- 首次启动目录选择器需要系统支持 Tk；若缺失 `_tkinter`，macOS 将自动调用 AppleScript，其他平台可先手动输入路径。

欢迎基于此结构继续扩展自动化脚本、权限审批、会话持久化等能力。

## 一键启动脚本

在仓库根目录执行：

```bash
./scripts/dev.sh
```

脚本会自动：

1. 创建/复用 `backend/.venv` 并安装后端依赖；
2. 启动 FastAPI 服务（默认端口 `9000`）；
3. 安装前端依赖并启动 Vite 开发服务器（默认端口 `5173`，自动配置 `VITE_API_BASE`）。

可通过环境变量 `API_PORT`、`WEB_PORT` 调整端口。例如：

```bash
API_PORT=9100 WEB_PORT=3000 ./scripts/dev.sh
```

退出前端（Ctrl+C）时脚本会自动停止后端进程。

## 清理 Codex CLI 日志

Codex CLI 会将每次会话的 rollout 写入 `~/.codex/sessions`，时间久了会占用大量磁盘。可以使用仓库提供的脚本按需清理：

```bash
# 仅查看将删除的文件
python scripts/clean_codex_sessions.py --dry-run

# 清理 30 天前的日志，并限制总容量不超过 2GB
python scripts/clean_codex_sessions.py --retention-days 30 --max-total-size 2G
```

如未设置 `CODEX_HOME`，脚本默认操作 `~/.codex`。
