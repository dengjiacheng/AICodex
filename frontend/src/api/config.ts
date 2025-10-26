import axios from 'axios';
import type { ConfigState } from '../types';

const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, '') || 'http://localhost:9000';

const client = axios.create({
  baseURL: API_BASE,
});

export async function updateGlobalConfig(patch: Partial<ConfigState>): Promise<void> {
  await client.post('/config', patch);
}

export async function selectWorkspace(): Promise<string> {
  const { data } = await client.post<{ path: string }>('/select-directory', {});
  return data.path;
}
