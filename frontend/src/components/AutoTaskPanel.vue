<template>
  <div class="auto-task-panel">
    <header class="panel-header">
      <div class="task-headline">
        <h3>{{ activeSession?.taskId ?? '暂无任务' }}</h3>
        <span
          v-if="activeSession"
          class="status-pill"
          :data-status="activeSession.status"
        >
          {{ sessionStatusLabel(activeSession.status) }}
        </span>
      </div>
      <p v-if="currentObjective" class="objective">
        {{ currentObjective }}
      </p>
    </header>

    <section class="timeline" ref="timelineRef">
      <article
        v-for="message in displayedMessages"
        :key="message.id"
        :class="['message', message.role, message.kind ? `kind-${message.kind}` : '']"
      >
        <header class="message-header">
          <span class="role">{{ renderRole(message.role, message.kind) }}</span>
          <span v-if="message.kind" class="badge">{{ renderKind(message.kind) }}</span>
          <span class="time" v-if="message.timestamp">{{ formatTime(message.timestamp) }}</span>
        </header>
        <div v-if="message.role === 'codex'" class="markdown" v-html="renderMarkdown(message.text)" />
        <pre v-else><code>{{ message.text }}</code></pre>
      </article>
      <div v-if="!displayedMessages.length" class="empty">等待任务执行…</div>
    </section>

    <section v-if="activeSession?.summaryMarkdown" class="summary">
      <h4>任务小结</h4>
      <div class="markdown" v-html="renderMarkdown(activeSession.summaryMarkdown)" />
    </section>

    <section v-if="activeSession?.tests?.length" class="tests">
      <h4>测试结果</h4>
      <table>
        <thead>
          <tr><th>命令</th><th>状态</th><th>详情</th></tr>
        </thead>
        <tbody>
          <tr v-for="(test, idx) in activeSession?.tests" :key="idx">
            <td><code>{{ test.command }}</code></td>
            <td><span :class="['test-status', test.status]">{{ testStatusLabel(test.status) }}</span></td>
            <td>{{ test.details || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="activeSession?.knowledgeUpdates?.length" class="knowledge">
      <h4>知识库更新建议</h4>
      <ul>
        <li v-for="(item, idx) in activeSession.knowledgeUpdates" :key="idx">
          <code>{{ item.path }}</code> — {{ item.summary || '待补充' }}
        </li>
      </ul>
    </section>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue';
import MarkdownIt from 'markdown-it';
import { useAutoTaskStore } from '../stores/autoTask';
import type { AutoTaskMessage, AutoTaskSessionRecord } from '../types';

const store = useAutoTaskStore();
const markdown = new MarkdownIt({ linkify: true, breaks: true });
const timelineRef = ref<HTMLElement | null>(null);

const sessions = computed(() => store.state.sessions);

const activeSession = computed<AutoTaskSessionRecord | null>(() => {
  const selectedId = store.state.selectedTaskId;
  if (selectedId && sessions.value[selectedId]) {
    return sessions.value[selectedId];
  }
  const first = Object.values(sessions.value)[0];
  return first ?? null;
});

const displayedMessages = computed<AutoTaskMessage[]>(() => activeSession.value?.messages ?? []);
const currentObjective = computed(() => {
  const session = activeSession.value;
  const currentTask = store.state.currentTask;
  if (session && currentTask && currentTask.id === session.taskId) {
    return currentTask.objective;
  }
  return '';
});

watch(displayedMessages, () => {
  requestAnimationFrame(() => {
    const el = timelineRef.value;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  });
});

function renderMarkdown(content: string): string {
  return markdown.render(content ?? '');
}

function renderRole(role: string, kind?: string): string {
  if (role === 'codex') return 'Codex';
  if (role === 'command') {
    return kind === 'command_error' ? '命令错误' : '命令执行';
  }
  if (role === 'user') return '用户';
  return '系统';
}

function renderKind(kind?: string): string {
  if (!kind) return '';
  const map: Record<string, string> = {
    command_start: '执行命令',
    command_output: '命令输出',
    command_error: '命令错误',
    command_execution: '命令完成',
    status: '状态',
    error: '错误',
    reasoning: '推理',
    thread_started: '线程启动',
    turn_started: '回合开始',
    turn_completed: '回合结束',
    item_command_execution_started: '命令开始',
    item_command_execution_updated: '命令进展',
    item_reasoning_completed: '推理完成',
  };
  return map[kind] ?? kind;
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
}

function sessionStatusLabel(status: AutoTaskSessionRecord['status']): string {
  switch (status) {
    case 'running':
      return '运行中';
    case 'success':
      return '成功';
    case 'failed':
      return '失败';
    case 'paused':
      return '已暂停';
    default:
      return '等待中';
  }
}

function testStatusLabel(status: string): string {
  switch (status) {
    case 'passed':
      return '通过';
    case 'failed':
      return '失败';
    case 'skipped':
      return '跳过';
    default:
      return status || '-';
  }
}

onMounted(() => {
  if (!store.state.selectedTaskId) {
    const first = Object.keys(sessions.value)[0];
    if (first) store.setSelectedTask(first);
  }
});
</script>

<style scoped>
.auto-task-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  min-height: 0;
}

.panel-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-headline {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-pill {
  font-size: 13px;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(63, 81, 181, 0.12);
  color: rgba(63, 81, 181, 0.9);
}

.status-pill[data-status='running'] {
  background: rgba(0, 150, 136, 0.12);
  color: #00796b;
}

.status-pill[data-status='failed'] {
  background: rgba(244, 67, 54, 0.15);
  color: #c62828;
}

.status-pill[data-status='success'] {
  background: rgba(76, 175, 80, 0.18);
  color: #2e7d32;
}

.objective {
  margin: 0;
  color: rgba(0, 0, 0, 0.65);
  font-size: 13px;
}

.timeline {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 4px 16px;
  overflow-y: auto;
  min-height: 0;
}

.message {
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  padding: 12px 16px;
  background: var(--card-bg, #ffffff);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message.system {
  border-left: 4px solid rgba(96, 125, 139, 0.5);
}

.message.codex {
  border-left: 4px solid rgba(0, 150, 136, 0.6);
}

.message.command {
  border-left: 4px solid rgba(3, 169, 244, 0.6);
}

.message.user {
  border-left: 4px solid rgba(63, 81, 181, 0.6);
}

.message-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
}

.message-header .role {
  font-weight: 600;
}

.message-header .time {
  margin-left: auto;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.4);
}

.badge {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(33, 150, 243, 0.12);
  color: #0d47a1;
  font-size: 12px;
}

.message pre {
  margin: 0;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 6px;
  padding: 8px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.message .markdown {
  background: rgba(0, 0, 0, 0.02);
  border-radius: 6px;
  padding: 8px;
}

.summary,
.tests,
.knowledge {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  padding-top: 12px;
}

.tests table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.tests th, .tests td {
  border: 1px solid rgba(0, 0, 0, 0.08);
  padding: 6px 8px;
  text-align: left;
}

.test-status {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(158, 158, 158, 0.15);
}

.test-status.passed {
  background: rgba(0, 150, 136, 0.15);
  color: #00695c;
}

.test-status.failed {
  background: rgba(244, 67, 54, 0.15);
  color: #c62828;
}

.empty {
  text-align: center;
  color: rgba(0, 0, 0, 0.45);
  padding: 24px 0;
}
</style>
