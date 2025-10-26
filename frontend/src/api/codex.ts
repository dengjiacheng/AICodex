import axios from 'axios';
import type { AppState, ConfigState, Session, SessionRoleInfo } from '../types';

export const CODEX_API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, '') || 'http://localhost:9000';

const codexClient = axios.create({
  baseURL: CODEX_API_BASE,
});

export async function fetchCodexState(): Promise<AppState> {
  const { data } = await codexClient.get<AppState>('/state');
  return data;
}

export async function createCodexSession(name?: string, color?: string): Promise<Session> {
  const payload: { name?: string; color?: string } = {};
  if (name) payload.name = name;
  if (color) payload.color = color;
  const { data } = await codexClient.post<{ session: Session }>('/sessions', payload);
  return data.session;
}

export async function startCodexSession(id: string): Promise<void> {
  await codexClient.post(`/sessions/${id}/start`, {});
}

export async function stopCodexSession(id: string): Promise<void> {
  await codexClient.post(`/sessions/${id}/stop`, {});
}

export async function sendCodexInput(id: string, text: string, forwardedBy?: string): Promise<void> {
  await codexClient.post(`/sessions/${id}/input`, { text, forwarded_by: forwardedBy });
}

export async function clearCodexSession(id: string): Promise<void> {
  await codexClient.post(`/sessions/${id}/clear`, {});
}

export async function saveCodexSession(id: string): Promise<string> {
  const { data } = await codexClient.post<{ path: string }>(`/sessions/${id}/save`, {});
  return data.path;
}

export async function deleteCodexSession(id: string): Promise<void> {
  await codexClient.delete(`/sessions/${id}`);
}

export async function updateCodexConfig(patch: Partial<ConfigState>): Promise<void> {
  await codexClient.post('/config', patch);
}

export async function selectCodexWorkspace(): Promise<string> {
  const { data } = await codexClient.post<{ path: string }>('/select-directory', {});
  return data.path;
}

export function createCodexWebSocket(): WebSocket {
  const wsUrl = (CODEX_API_BASE.startsWith('https') ? CODEX_API_BASE.replace('https', 'wss') : CODEX_API_BASE.replace('http', 'ws'));
  return new WebSocket(`${wsUrl.replace(/\/$/, '')}/ws`);
}

export function codexRoleColor(role: SessionRoleInfo): string {
  return role.color || '#1976d2';
}
