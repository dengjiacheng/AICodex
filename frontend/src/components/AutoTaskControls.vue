<template>
  <section class="auto-task-controls">
    <header class="controls-header">
      <h2>自动任务</h2>
      <span :class="['status-pill', store.state.status]">{{ statusLabel }}</span>
    </header>

    <div class="controls-buttons">
      <button type="button" @click="handleStart" :disabled="store.state.status === 'running'">启动</button>
      <button type="button" @click="handleStop" :disabled="store.state.status !== 'running'">暂停</button>
      <button type="button" @click="handleBootstrap" :disabled="bootstrapping">初始化</button>
    </div>

    <section v-if="store.state.currentTask" class="current-task">
      <h3>当前任务</h3>
      <p class="task-id">{{ store.state.currentTask.id }}</p>
      <p class="task-title">{{ store.state.currentTask.title }}</p>
      <p class="task-objective">{{ store.state.currentTask.objective }}</p>
      <div v-if="store.isClarificationNeeded" class="clarification">
        <label>需要澄清：</label>
        <textarea v-model="clarificationInput" placeholder="回复自动任务澄清..." rows="3" />
        <button type="button" :disabled="!clarificationInput.trim()" @click="submitClarification">发送澄清</button>
      </div>
    </section>

    <section v-if="store.state.alerts.length" class="alerts">
      <h3>警报</h3>
      <ul>
        <li v-for="alert in store.state.alerts" :key="alert.id" :class="alert.level">
          <span class="when">{{ formatTime(alert.timestamp) }}</span>
          <span>{{ alert.message }}</span>
        </li>
      </ul>
    </section>

    <section class="session-list">
      <header>
        <h3>任务会话</h3>
        <span class="count">共 {{ sessions.length }} 项</span>
      </header>
      <ul>
        <li
          v-for="session in sessions"
          :key="session.taskId"
          :class="['session-item', { active: session.taskId === selectedTaskId }]"
          @click="selectSession(session.taskId)"
        >
          <div class="session-header">
            <span class="session-task">{{ session.taskId }}</span>
            <span class="session-status" :data-status="session.status">{{ sessionStatusLabel(session.status) }}</span>
          </div>
          <p class="session-summary">{{ sessionSummary(session) }}</p>
        </li>
      </ul>
    </section>
  </section>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue';
import { bootstrapAutoTask } from '../api/autoTask';
import { useAutoTaskStore } from '../stores/autoTask';
import type { AutoTaskSessionRecord } from '../types';

const props = defineProps<{ workspace?: string }>();
const store = useAutoTaskStore();
const clarificationInput = ref('');
const bootstrapping = ref(false);

const sessions = computed(() => Object.values(store.state.sessions).sort((a, b) => {
  const aTime = a.startedAt ? new Date(a.startedAt).getTime() : 0;
  const bTime = b.startedAt ? new Date(b.startedAt).getTime() : 0;
  return bTime - aTime;
}));

const statusLabel = computed(() => {
  switch (store.state.status) {
    case 'running':
      return '运行中';
    case 'pausing':
      return '暂停中';
    case 'paused':
      return '已暂停';
    case 'waiting_clarification':
      return '待澄清';
    case 'completed':
      return '已完成';
    case 'error':
      return '异常';
    default:
      return '就绪';
  }
});

const selectedTaskId = computed(() => store.state.selectedTaskId ?? sessions.value[0]?.taskId ?? null);

watch(sessions, (list) => {
  if (!list.length) {
    store.setSelectedTask(null);
    return;
  }
  if (!store.state.selectedTaskId) {
    store.setSelectedTask(list[0].taskId);
  }
});

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
      return '待开始';
  }
}

function sessionSummary(session: AutoTaskSessionRecord): string {
  if (session.summaryMarkdown) {
    return session.summaryMarkdown.replace(/\s+/g, ' ').slice(0, 80);
  }
  const messages = session.messages ?? [];
  if (messages.length) {
    const last = messages[messages.length - 1];
    return last.text.replace(/\s+/g, ' ').slice(0, 80);
  }
  return '尚无输出';
}

async function handleStart(): Promise<void> {
  try {
    await store.startLoop();
  } catch (error) {
    alert('启动自动任务失败，请查看后端日志。');
    console.error(error);
  }
}

async function handleStop(): Promise<void> {
  try {
    await store.stopLoop();
  } catch (error) {
    console.error(error);
  }
}

async function handleBootstrap(): Promise<void> {
  if (bootstrapping.value) return;
  bootstrapping.value = true;
  try {
    await bootstrapAutoTask(props.workspace);
    alert('已初始化 .codex 目录');
  } catch (error: any) {
    console.error(error);
    const detail = error?.response?.data?.detail ?? '初始化失败，请检查后端日志。';
    alert(detail);
  } finally {
    bootstrapping.value = false;
  }
}

async function submitClarification(): Promise<void> {
  const text = clarificationInput.value.trim();
  if (!text) return;
  try {
    await store.submitClarification(text);
    clarificationInput.value = '';
  } catch (error) {
    console.error(error);
  }
}

function selectSession(taskId: string): void {
  store.setSelectedTask(taskId);
}

onMounted(() => {
  if (!store.state.selectedTaskId) {
    const first = sessions.value[0]?.taskId;
    if (first) store.setSelectedTask(first);
  }
});
</script>

<style scoped>
.auto-task-controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 0;
}

.controls-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.controls-buttons {
  display: flex;
  gap: 8px;
}

.controls-buttons button {
  flex: 1;
  padding: 8px 0;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: transparent;
  cursor: pointer;
}

.controls-buttons button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.current-task {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.current-task .task-id {
  font-weight: 600;
}

.current-task .clarification {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.current-task textarea {
  width: 100%;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  padding: 8px;
  resize: vertical;
}

.current-task button {
  align-self: flex-end;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: transparent;
  cursor: pointer;
}

.alerts ul {
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.alerts li {
  list-style: none;
  padding: 8px;
  border-radius: 6px;
  background: rgba(255, 193, 7, 0.1);
}

.alerts li.error {
  background: rgba(244, 67, 54, 0.12);
}

.alerts .when {
  display: block;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.5);
}

.session-list ul {
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.session-item {
  list-style: none;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid rgba(63, 81, 181, 0.15);
  background: #fff;
  cursor: pointer;
  transition: border-color 0.2s ease;
}

.session-item.active {
  border-color: rgba(63, 81, 181, 0.45);
  box-shadow: 0 4px 10px rgba(63, 81, 181, 0.12);
}

.session-summary {
  margin: 4px 0 0;
  color: rgba(0, 0, 0, 0.6);
  font-size: 13px;
}
</style>
