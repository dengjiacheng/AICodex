<template>
  <div class="app-shell" :class="{ 'dark-theme': isDarkTheme }">
    <aside class="sidebar">
      <header class="sidebar-header">
        <h1>Codex 控制台</h1>
      </header>

      <section class="config-panel">
        <h2>全局配置</h2>
        <div class="config-group">
          <label>
            <span>命令</span>
            <input
              v-model="configForm.command"
              placeholder="默认 codex"
              @blur="persistConfigField('command', configForm.command)"
            />
          </label>
          <label>
            <span>参数</span>
            <input
              v-model="configForm.args"
              placeholder="附加参数"
              @blur="persistConfigField('args', configForm.args)"
            />
          </label>
          <label class="workspace-field">
            <span>工作目录</span>
            <div class="workspace-input">
              <input :value="configForm.workspace" readonly />
              <button type="button" :disabled="selectingWorkspace" @click="openWorkspacePicker">
                {{ selectingWorkspace ? '选择中…' : '选择' }}
              </button>
            </div>
          </label>
        </div>

        <div class="config-group">
          <DropdownField
            label="模型"
            :value="configForm.model"
            :options="modelOptions"
            tooltip="选择 Codex 模型版本"
            @update="value => handleSelectConfig('model', value)"
          />
          <DropdownField
            label="推理强度"
            :value="configForm.reasoning"
            :options="reasoningOptions"
            tooltip="推理强度越高越细致，但处理时间更久"
            @update="value => handleSelectConfig('reasoning', value)"
          />
          <DropdownField
            label="总结风格"
            :value="configForm.summary"
            :options="summaryOptions"
            tooltip="控制 Codex 输出总结的风格"
            @update="value => handleSelectConfig('summary', value)"
          />
        </div>
      </section>

    </aside>

    <main class="main-pane">
      <header class="main-tabs">
        <div class="tabs">
          <button
            v-for="tab in mainTabs"
            :key="tab.id"
            type="button"
            :class="['main-tab', { active: tab.id === activeMainTab }]"
            @click="activeMainTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </div>
      </header>

      <section v-if="activeMainTab === 'codex'" class="codex-pane">
        <section v-if="activeSession" class="timeline" ref="timelineRef">
          <article
            v-for="message in activeSession.messages"
            :key="message.id"
            :class="['message', message.role]"
          >
            <header>
              <button type="button" class="collapse" @click="toggleMessage(message.id)">
                {{ isExpanded(message.id) ? '▾' : '▸' }}
              </button>
              <span class="role">{{ renderMessageRole(message) }}</span>
              <span v-if="message.kind" class="kind">{{ renderMessageKind(message) }}</span>
              <span class="timestamp">{{ formatTime(message.timestamp) }} · {{ currentThreadId || activeSessionId }}</span>
              <span v-if="!isExpanded(message.id)" class="preview">{{ messagePreview(message) }}</span>
              <button type="button" class="copy" @click="copyMessage(message)">复制</button>
            </header>
            <div v-if="isExpanded(message.id)">
              <div
                v-if="message.role === 'codex' && message.kind === 'agent_message'"
                class="markdown"
                v-html="renderMarkdown(message)"
              ></div>
              <pre v-else>
                <code
                  v-for="(part, idx) in message.parts"
                  :key="idx"
                  :class="{ error: part.is_error }"
                >{{ part.text }}</code>
              </pre>
            </div>
          </article>
        </section>
        <section v-else class="empty">正在准备会话…</section>

        <footer v-if="activeSession" class="composer">
          <textarea
            v-model="composerText"
            placeholder="发送指令给 Codex……"
            rows="4"
            @keydown.enter.exact.prevent="send"
            @keydown.shift.enter.stop
          ></textarea>
          <div class="composer-actions">
            <span v-if="tokenHint" class="token-hint">{{ tokenHint }}</span>
            <button type="button" @click="startNewSession">新会话</button>
            <button type="button" @click="send">发送 (Enter)</button>
            <button type="button" @click="clearComposer">清空</button>
          </div>
        </footer>
      </section>

      <section v-else class="auto-placeholder">
        <div class="placeholder-card">
          <h2>AUTO CODEX</h2>
          <p>即将上线，敬请期待。</p>
        </div>
      </section>

    </main>
  </div>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import MarkdownIt from 'markdown-it';
import DropdownField from './components/DropdownField.vue';
import { modelOptions, reasoningOptions, summaryOptions } from './options';
import type {
  AppState,
  ChatMessage,
  ConfigState,
  Session,
  TokenUsage,
} from './types';
import {
  createSession,
  createWebSocket,
  fetchState,
  selectWorkspace,
  sendInput,
  updateConfig,
} from './api';

const state = ref<AppState | null>(null);
const composerText = ref('');
const timelineRef = ref<HTMLElement | null>(null);
const markdown = new MarkdownIt({ linkify: true, breaks: true });
const expandedMessages = reactive(new Set<string>());
const selectingWorkspace = ref(false);
const ensuringSession = ref(false);
let ws: WebSocket | null = null;
const activeSessionId = ref<string | null>(null);

const configForm = reactive<ConfigState>({
  command: '',
  args: '',
  workspace: '',
  model: '',
  reasoning: '',
  summary: '',
  approval: '',
  sandbox: '',
});

const sessions = computed(() => state.value?.sessions ?? []);
const mainTabOptions = [
  { id: 'codex' as const, label: 'CODEX' },
  { id: 'auto' as const, label: 'AUTO CODEX' },
] as const;
type MainTabId = (typeof mainTabOptions)[number]['id'];
const activeMainTab = ref<MainTabId>('codex');
const activeSession = computed<Session | undefined>(() => {
  const list = sessions.value;
  if (!list.length) return undefined;
  if (activeSessionId.value) {
    const found = list.find((item) => item.id === activeSessionId.value);
    if (found) return found;
  }
  return list[0];
});

const currentThreadId = computed(() => activeSession.value?.thread_id ?? '');

const mainTabs = computed(() =>
  mainTabOptions.map((tab) => {
    if (tab.id === 'codex' && activeSession.value?.status === 'running') {
      return { ...tab, label: 'CODEX（处理中…）' };
    }
    return tab;
  }),
);

const isDarkTheme = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;

const tokenHint = computed(() => {
  const usage = activeSession.value?.token_usage;
  if (!usage) return '';
  const last = usage.last ?? usage.total ?? {};
  const total = usage.total ?? {};
  const fmt = (value?: number) =>
    typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '-';

  const details: string[] = [
    `本次 ${fmt(last.total_tokens)}`,
    `输入 ${fmt(last.input_tokens)}`,
    `输出 ${fmt(last.output_tokens)}`,
  ];

  if (typeof last.reasoning_output_tokens === 'number') {
    details.push(`推理 ${fmt(last.reasoning_output_tokens)}`);
  }
  if (typeof last.cached_input_tokens === 'number' && last.cached_input_tokens > 0) {
    details.push(`缓存 ${fmt(last.cached_input_tokens)}`);
  }

  const totalPart = `累计 ${fmt(total.total_tokens)}`;
  return `${details.join(' · ')} ｜ ${totalPart}`;
});

const kindLabels: Record<string, string> = {
  command_context: '命令',
  command_start: '命令开始',
  command_update: '命令输出',
  command_complete: '命令完成',
  stdout: '标准输出',
  stderr: '标准错误',
  reasoning: '推理',
  agent_message: '回复',
  file_change: '文件变更',
  mcp_tool: 'MCP 调用',
  web_search: '网页搜索',
  todo_list: '待办更新',
  command_execution: '命令执行',
  error: '错误',
  input: '输入',
};

function renderMessageRole(message: ChatMessage): string {
  switch (message.role) {
    case 'user':
      return message.forwarded_by ? `用户（来自 ${message.forwarded_by}）` : '用户';
    case 'codex':
      return 'Codex';
    default:
      return message.forwarded_by ? `系统（来自 ${message.forwarded_by}）` : '系统';
  }
}

function renderMessageKind(message: ChatMessage): string {
  if (!message.kind) return '';
  return kindLabels[message.kind] ?? message.kind;
}

async function send(): Promise<void> {
  const text = composerText.value.trim();
  if (!text) {
    return;
  }
  const flushText = composerText.value;
  composerText.value = '';
  const session = activeSession.value;
  if (!session) return;
  if (session.status === 'running') {
    // 如果上一次没有跑完，把文本恢复并提示
    composerText.value = flushText;
    alert('当前会话仍在处理中，请稍后发送。');
    return;
  }
  try {
    await sendCodexInput(session.id, flushText);
  } catch (error) {
    composerText.value = flushText;
    const detail =
      (error as any)?.response?.data?.detail ??
      (error instanceof Error ? error.message : String(error));
    console.error('发送消息失败', error);
    alert(`发送失败：${detail}`);
  }
}

function clearComposer(): void {
  composerText.value = '';
}

function copyMessage(message: ChatMessage): void {
  const text = message.parts.map((part) => part.text).join('');
  navigator.clipboard?.writeText(text).catch(() => {});
}

function renderMarkdown(message: ChatMessage): string {
  const text = message.parts.map((part) => part.text).join('');
  return markdown.render(text);
}

function toggleMessage(id: string): void {
  if (expandedMessages.has(id)) {
    expandedMessages.delete(id);
  } else {
    expandedMessages.add(id);
  }
}

function isExpanded(id: string): boolean {
  return expandedMessages.has(id);
}

function messagePreview(message: ChatMessage): string {
  if (!message.parts.length) return '';
  const text = message.parts.map((part) => part.text).join('').replace(/\s+/g, ' ').trim();
  return text.slice(0, 60) + (text.length > 60 ? '…' : '');
}

function formatTime(timestamp?: string | null): string {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp ?? '';
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  return formatter.format(date).replace(/\//g, '/');
}

function setState(next: AppState): void {
  state.value = next;
  Object.assign(configForm, next.config);
  const sessionList = next.sessions;
  if (!sessionList.length) {
    activeSessionId.value = null;
  } else if (!activeSessionId.value || !sessionList.some((item) => item.id === activeSessionId.value)) {
    activeSessionId.value = sessionList[0].id;
  }
  for (const session of next.sessions) {
    for (const message of session.messages) {
      expandedMessages.add(message.id);
    }
  }
}

function applyMessages(sessionId: string, messages: ChatMessage[]): void {
  if (!state.value) return;
  const session = state.value.sessions.find((item) => item.id === sessionId);
  if (!session) {
    void refreshState();
    return;
  }
  for (const message of messages) {
    const index = session.messages.findIndex((item) => item.id === message.id);
    if (index >= 0) {
      session.messages.splice(index, 1, message);
    } else {
      session.messages.push(message);
    }
    expandedMessages.add(message.id);
  }
}

function applyTokenUpdate(sessionId: string, usage: TokenUsage): void {
  if (!state.value) return;
  const session = state.value.sessions.find((item) => item.id === sessionId);
  if (!session) return;
  session.token_usage = usage;
}

async function ensureDefaultSession(snapshot: AppState): Promise<void> {
  if (ensuringSession.value) return;
  if (snapshot.sessions.length > 0) return;
  ensuringSession.value = true;
  try {
    const session = await createCodexSession();
    activeSessionId.value = session.id;
    if (state.value) {
      state.value.sessions.push(session);
      for (const message of session.messages) {
        expandedMessages.add(message.id);
      }
    }
  } finally {
    ensuringSession.value = false;
  }
}

async function refreshState(): Promise<void> {
  const data = await fetchCodexState();
  setState(data);
  await ensureDefaultSession(data);
}

async function persistConfigField(field: keyof ConfigState, value: string): Promise<void> {
  if (field === 'command') {
    const trimmed = value.trim();
    if (!trimmed) {
      alert('命令不能为空');
      configForm.command = state.value?.config.command ?? '';
      return;
    }
    value = trimmed;
    configForm.command = trimmed;
  }
  if (state.value) {
    (state.value.config as Record<string, string>)[field] = value;
    if (field === 'workspace') {
      state.value.workspace = value;
    }
  }
  try {
    await updateCodexConfig({ [field]: value } as Partial<ConfigState>);
  } catch (error) {
    await refreshState();
  }
}

function handleSelectConfig(field: keyof ConfigState, value: string): void {
  (configForm as Record<string, string>)[field] = value;
  void persistConfigField(field, value);
}

async function openWorkspacePicker(): Promise<void> {
  if (selectingWorkspace.value) return;
  selectingWorkspace.value = true;
  try {
    const path = await selectCodexWorkspace();
    configForm.workspace = path;
    if (state.value) {
      state.value.workspace = path;
      state.value.config.workspace = path;
    }
  } catch (error: any) {
    const detail = error?.response?.data?.detail;
    if (detail && detail !== '未选择目录') {
      alert(detail);
    }
  } finally {
    selectingWorkspace.value = false;
  }
}

async function startNewSession(): Promise<void> {
  try {
    const session = await createCodexSession();
    if (state.value) {
      state.value.sessions.push(session);
      for (const message of session.messages) {
        expandedMessages.add(message.id);
      }
    }
    activeSessionId.value = session.id;
    composerText.value = '';
  } catch (error) {
    console.error('Failed to create new session', error);
    alert('创建新会话失败，请稍后再试。');
  }
}

onMounted(async () => {
  await refreshState();
  ws = createCodexWebSocket();
  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === 'state') {
      setState(payload.data as AppState);
      void ensureDefaultSession(payload.data as AppState);
    } else if (payload.type === 'message') {
      applyMessages(payload.session_id as string, payload.messages as ChatMessage[]);
    } else if (payload.type === 'token_update') {
      applyTokenUpdate(payload.session_id as string, payload.usage as TokenUsage);
    } else {
      void refreshState();
    }
  };
  ws.onclose = () => {
    setTimeout(() => {
      if (!ws || ws.readyState === WebSocket.CLOSED) {
        ws = createCodexWebSocket();
      }
    }, 2000);
  };
});

onBeforeUnmount(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
  }
});

watch(
  () => activeSession.value?.messages.length,
  () => {
    requestAnimationFrame(() => {
      const container = timelineRef.value;
      if (!container) return;
      container.scrollTop = container.scrollHeight;
    });
  },
);
</script>

<style scoped>
.app-shell {
  display: grid;
  grid-template-columns: 360px 1fr;
  height: 100vh;
  overflow: hidden;
  background: var(--surface-bg, #f0f2f5);
  color: var(--text-color, #1f1f1f);
}

.dark-theme {
  --surface-bg: #1f1f23;
  --text-color: #f5f5f5;
  --card-bg: #2a2a31;
  --border-color: rgba(255, 255, 255, 0.08);
}

.sidebar {
  padding: 24px;
  border-right: 1px solid var(--border-color, rgba(0, 0, 0, 0.08));
  background: var(--card-bg, #ffffff);
  display: flex;
  flex-direction: column;
  gap: 24px;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sidebar-header h1 {
  margin: 0;
}

.config-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 12px;
  padding: 16px;
}

.config-panel h2 {
  margin: 0;
  font-size: 18px;
}

.config-group {
  display: grid;
  gap: 12px;
}

.config-group label,
:deep(.dropdown-field) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-group input {
  border-radius: 8px;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.12));
  padding: 10px;
  background: transparent;
  color: inherit;
}

.workspace-input {
  display: flex;
  align-items: center;
  gap: 8px;
}

.workspace-input input {
  flex: 1;
  cursor: default;
}

.workspace-input button {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.12));
  background: transparent;
  cursor: pointer;
}

.workspace-input button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.main-pane {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--surface-bg, #f0f2f5);
  overflow: hidden;
}

.main-tabs {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-color, rgba(0, 0, 0, 0.08));
  background: var(--card-bg, #ffffff);
  backdrop-filter: blur(6px);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}

.tabs {
  display: flex;
  gap: 8px;
  align-items: center;
}

.main-tab {
  padding: 10px 22px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: rgba(63, 81, 181, 0.08);
  cursor: pointer;
  font-weight: 600;
  color: inherit;
  transition: all 0.2s ease;
}

.main-tab.active {
  border-color: rgba(63, 81, 181, 0.35);
  background: rgba(63, 81, 181, 0.22);
  box-shadow: 0 6px 16px rgba(63, 81, 181, 0.12);
}

.main-tab:not(.active):hover {
  background: rgba(63, 81, 181, 0.14);
}
.codex-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.timeline {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.auto-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-bg, #f0f2f5);
}

.placeholder-card {
  padding: 32px 40px;
  border-radius: 16px;
  background: var(--card-bg, #ffffff);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.12);
  text-align: center;
  max-width: 320px;
}

.placeholder-card h2 {
  margin: 0 0 12px;
  font-size: 20px;
}

.placeholder-card p {
  margin: 0;
  color: rgba(15, 23, 42, 0.6);
}

.message {
  border-radius: 12px;
  padding: 16px;
  background: var(--card-bg, #ffffff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.message.system {
  border-left: 4px solid #607d8b;
}

.message.user {
  border-left: 4px solid #3f51b5;
}

.message.codex {
  border-left: 4px solid #009688;
}

.message header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.message header .kind {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.08);
  font-size: 12px;
  color: rgba(15, 23, 42, 0.65);
}

.message header .preview {
  flex: 1;
  color: rgba(0, 0, 0, 0.6);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message header .copy {
  margin-left: auto;
  border: none;
  background: transparent;
  cursor: pointer;
}

.message header .collapse {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 16px;
}

pre {
  margin: 0;
  background: rgba(15, 23, 42, 0.05);
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
}

code {
  display: block;
  white-space: pre-wrap;
  word-break: break-word;
}

code.error {
  color: #f44336;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3) {
  margin-top: 16px;
}

.markdown :deep(pre) {
  background: rgba(15, 23, 42, 0.08);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
}

.composer {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color, rgba(0, 0, 0, 0.08));
  background: var(--card-bg, #ffffff);
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: sticky;
  bottom: 0;
  z-index: 10;
}

textarea {
  width: 100%;
  border-radius: 10px;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.12));
  padding: 12px;
  resize: vertical;
  min-height: 100px;
  background: transparent;
  color: inherit;
}

.composer-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
}

.composer-actions .token-hint {
  margin-right: auto;
  font-variant-numeric: tabular-nums;
  color: rgba(0, 0, 0, 0.6);
}

.composer-actions button {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.12));
  background: transparent;
  cursor: pointer;
}

.empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: rgba(0, 0, 0, 0.6);
}

</style>
