import { computed, onBeforeUnmount, reactive } from 'vue';
import { defineStore } from 'pinia';
import {
  createAutoTaskWebSocket,
  fetchAutoTaskState,
  sendClarification,
  startAutoTask,
  stopAutoTask,
} from '../api/autoTask';
import type {
  AutoTaskAlert,
  AutoTaskCurrent,
  AutoTaskEvent,
  AutoTaskMetrics,
  AutoTaskMessage,
  AutoTaskSessionRecord,
  AutoTaskStatePayload,
  AutoTaskStatus,
} from '../types';

interface AutoTaskState {
  status: AutoTaskStatus;
  currentTask: AutoTaskCurrent | null;
  threadId: string | null;
  attempts: number;
  lastError: string | null;
  wsConnected: boolean;
  sessions: Record<string, AutoTaskSessionRecord>;
  alerts: AutoTaskAlert[];
  metrics: AutoTaskMetrics | null;
  selectedTaskId: string | null;
}

export const useAutoTaskStore = defineStore('auto-task', () => {
  const state = reactive<AutoTaskState>({
    status: 'idle',
    currentTask: null,
    threadId: null,
    attempts: 0,
    lastError: null,
    wsConnected: false,
    sessions: {},
    alerts: [],
    metrics: null,
    selectedTaskId: null,
  });

  const isClarificationNeeded = computed(
    () => state.currentTask?.status === 'needs_clarification',
  );

  let ws: WebSocket | null = null;

  async function loadInitialState(): Promise<void> {
    const snapshot = await fetchAutoTaskState();
    applyState(snapshot);
  }

  function applyState(payload: AutoTaskStatePayload): void {
    state.status = payload.status;
    state.currentTask = payload.current_task;
    state.threadId = payload.thread_id ?? null;
    state.attempts = payload.attempts ?? 0;
    state.lastError = payload.last_error ?? null;
  }

  function ensureSession(taskId: string): AutoTaskSessionRecord {
    if (!state.sessions[taskId]) {
      state.sessions[taskId] = {
        taskId,
        status: 'pending',
        events: [],
        messages: [],
        retries: 0,
      };
    }
    return state.sessions[taskId];
  }



  function setSelectedTask(taskId: string | null): void {
    state.selectedTaskId = taskId;
  }
  function generateId(): string {
    if (typeof globalThis.crypto?.randomUUID === 'function') {
      return globalThis.crypto.randomUUID();
    }
    return `auto-task-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
  function handleEvent(event: AutoTaskEvent): void {
    switch (event.type) {
      case 'state':
        applyState(event.data as AutoTaskStatePayload);
        break;
      case 'task.update': {
        const taskId = String(event.task_id ?? '');
        if (!taskId) break;
        const session = ensureSession(taskId);
        session.status = (event.status as AutoTaskSessionRecord['status']) ?? session.status;
        session.retries = Number(event.attempts ?? session.retries);
        if (event.started_at) session.startedAt = event.started_at as string;
        if (event.ended_at) session.endedAt = event.ended_at as string;
        break;
      }
      case 'auto_task.message': {
        const taskId = String(event.task_id ?? '');
        if (!taskId) break;
        const message = event.message as AutoTaskMessage | undefined;
        if (!message) break;
        const session = ensureSession(taskId);
        if (!session.messages) session.messages = [];
        session.messages.push(message);
        if (!session.startedAt) session.startedAt = message.timestamp ?? new Date().toISOString();
        break;
      }
      case 'cli.event': {
        const taskId = String(event.task_id ?? '');
        if (!taskId) break;
        const session = ensureSession(taskId);
        session.events.push(event.event ?? event);
        break;
      }
      case 'summary.ready': {
        const taskId = String(event.task_id ?? '');
        if (!taskId) break;
        const session = ensureSession(taskId);
        session.summaryMarkdown = String(event.markdown ?? '');
        if (Array.isArray(event.tests)) {
          session.tests = event.tests as AutoTaskSessionRecord['tests'];
        }
        if (Array.isArray(event.knowledge_updates)) {
          session.knowledgeUpdates = event.knowledge_updates as AutoTaskSessionRecord['knowledgeUpdates'];
        }
        break;
      }
      case 'knowledge.updated': {
        const taskId = String(event.task_id ?? '');
        if (!taskId) break;
        const session = ensureSession(taskId);
        if (Array.isArray(event.updates)) {
          session.knowledgeUpdates = event.updates as AutoTaskSessionRecord['knowledgeUpdates'];
        }
        break;
      }
      case 'alert': {
        const alert: AutoTaskAlert = {
          id: String(event.id ?? generateId()),
          level: (event.level as AutoTaskAlert['level']) ?? 'info',
          message: String(event.message ?? ''),
          timestamp: String(event.timestamp ?? new Date().toISOString()),
        };
        state.alerts.unshift(alert);
        break;
      }
      case 'metric':
        state.metrics = {
          timestamp: String(event.timestamp ?? new Date().toISOString()),
          tasks_completed: Number(event.tasks_completed ?? 0),
          failures: Number(event.failures ?? 0),
          total_tokens: typeof event.total_tokens === 'number' ? (event.total_tokens as number) : undefined,
        };
        break;
      case 'clarification':
      case 'clarification.received':
      case 'clarification.processed': {
        const taskId = String(event.task_id ?? '');
        const session = taskId ? ensureSession(taskId) : undefined;
        if (session) {
          session.events.push(event);
        }
        break;
      }
      case 'orchestrator.info': {
        const taskId = String(event.task_id ?? '');
        const session = taskId ? ensureSession(taskId) : undefined;
        if (session) {
          session.events.push(event);
        }
        break;
      }
      default:
        break;
    }
  }

  function connectWebSocket(): void {
    if (ws) {
      return;
    }
    ws = createAutoTaskWebSocket();
    ws.onopen = () => {
      state.wsConnected = true;
    };
    ws.onclose = () => {
      state.wsConnected = false;
      ws = null;
      setTimeout(connectWebSocket, 2000);
    };
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as AutoTaskEvent;
        handleEvent(payload);
      } catch (error) {
        console.error('Failed to parse auto task event', error);
      }
    };
    ws.onerror = () => {
      state.wsConnected = false;
    };
  }

  async function startLoop(): Promise<void> {
    await startAutoTask();
  }

  async function stopLoop(): Promise<void> {
    await stopAutoTask();
  }

  async function submitClarification(message: string): Promise<void> {
    await sendClarification(message);
  }

  function resetSessions(): void {
    state.sessions = {};
  }

  onBeforeUnmount(() => {
    if (ws) {
      ws.close();
      ws = null;
    }
  });

  return {
    state,
    isClarificationNeeded,
    loadInitialState,
    connectWebSocket,
    startLoop,
    stopLoop,
    submitClarification,
    resetSessions,
    setSelectedTask,
  };
});
