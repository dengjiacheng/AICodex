import axios from 'axios';
import type { AppState, Session, SessionRoleInfo } from '../types';

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

export async function sendCodexInput(id: string, text: string, forwardedBy?: string): Promise<void> {
  await codexClient.post(`/sessions/${id}/input`, { text, forwarded_by: forwardedBy });
}

export function createCodexWebSocket(): WebSocket {
  const wsUrl = CODEX_API_BASE.startsWith('https') ? CODEX_API_BASE.replace('https', 'wss') : CODEX_API_BASE.replace('http', 'ws');
  return new WebSocket(`${wsUrl.replace(/\/$/, '')}/ws`);
}

export function codexRoleColor(role: SessionRoleInfo): string {
  return role.color || '#1976d2';
}
