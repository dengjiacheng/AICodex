import axios from 'axios';
import type { AppState, ConfigState, Session, SessionRoleInfo } from './types';

export const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, '') || 'http://localhost:9000';
export const client = axios.create({
  baseURL: API_BASE,
});

export async function fetchState(): Promise<AppState> {
  const { data } = await client.get<AppState>('/state');
  return data;
}

export async function createSession(name?: string, color?: string): Promise<Session> {
  const payload: { name?: string; color?: string } = {};
  if (name) payload.name = name;
  if (color) payload.color = color;
  const { data } = await client.post<{ session: Session }>('/sessions', payload);
  return data.session;
}

export async function startSession(id: string): Promise<void> {
  await client.post(`/sessions/${id}/start`, {});
}

export async function stopSession(id: string): Promise<void> {
  await client.post(`/sessions/${id}/stop`, {});
}

export async function sendInput(id: string, text: string, forwardedBy?: string): Promise<void> {
  await client.post(`/sessions/${id}/input`, { text, forwarded_by: forwardedBy });
}

export async function clearSession(id: string): Promise<void> {
  await client.post(`/sessions/${id}/clear`, {});
}

export async function saveSession(id: string): Promise<string> {
  const { data } = await client.post<{ path: string }>(`/sessions/${id}/save`, {});
  return data.path;
}

export async function deleteSession(id: string): Promise<void> {
  await client.delete(`/sessions/${id}`);
}

export async function updateConfig(patch: Partial<ConfigState>): Promise<void> {
  await client.post('/config', patch);
}

export async function selectWorkspace(): Promise<string> {
  const { data } = await client.post<{ path: string }>('/select-directory', {});
  return data.path;
}

export function createWebSocket(): WebSocket {
  const wsUrl = (API_BASE.startsWith('https') ? API_BASE.replace('https', 'wss') : API_BASE.replace('http', 'ws'));
  return new WebSocket(`${wsUrl.replace(/\/$/, '')}/ws`);
}

export function roleColor(role: SessionRoleInfo): string {
  return role.color || '#1976d2';
}
