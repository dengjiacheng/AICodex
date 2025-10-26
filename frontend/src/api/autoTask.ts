import { API_BASE, client } from '../api';
import type { AutoTaskStatePayload } from '../types';

export async function fetchAutoTaskState(): Promise<AutoTaskStatePayload> {
  const { data } = await client.get<AutoTaskStatePayload>('/auto-task/state');
  return data;
}

export async function startAutoTask(): Promise<void> {
  await client.post('/auto-task/start', {});
}

export async function stopAutoTask(): Promise<void> {
  await client.post('/auto-task/stop', {});
}

export async function sendClarification(message: string): Promise<void> {
  await client.post('/auto-task/ack', { message });
}

export async function bootstrapAutoTask(workspace?: string): Promise<void> {
  await client.post('/auto-task/bootstrap', { workspace });
}

export async function fetchTaskSummary(taskId: string): Promise<string> {
  const { data } = await client.get<{ summary: string }>(`/auto-task/tasks/${taskId}`);
  return data.summary;
}

export function createAutoTaskWebSocket(): WebSocket {
  const wsBase = API_BASE.startsWith('https') ? API_BASE.replace('https', 'wss') : API_BASE.replace('http', 'ws');
  return new WebSocket(`${wsBase}/auto-task/ws`);
}
