export interface MessagePart {
  text: string;
  is_error: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'codex' | 'system' | 'command';
  timestamp: string;
  parts: MessagePart[];
  kind?: string | null;
  forwarded_by?: string | null;
  origin_session?: string | null;
}

export interface RoleTemplate {
  id: string;
  name: string;
  color: string;
  description?: string;
}

export interface SessionRoleInfo extends RoleTemplate {
  color: string;
}

export interface Session {
  id: string;
  role: SessionRoleInfo;
  command: string;
  args: string;
  workspace: string;
  model: string;
  reasoning: string;
  summary: string;
  approval: string;
  sandbox: string;
  status: string;
  status_detail?: string | null;
  messages: ChatMessage[];
  token_usage?: TokenUsage | null;
}

export interface TokenUsage {
  total?: TokenBreakdown;
  last?: TokenBreakdown;
  model_context_window?: number;
  rate_limits?: Record<string, unknown>;
  timestamp?: string;
}

export interface TokenBreakdown {
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
  reasoning_output_tokens?: number;
  total_tokens?: number;
}

export interface ConfigState {
  command: string;
  args: string;
  workspace: string;
  model: string;
  reasoning: string;
  summary: string;
  approval: string;
  sandbox: string;
}

export interface AppState {
  workspace: string;
  config: ConfigState;
  role_templates: RoleTemplate[];
  sessions: Session[];
}

export interface ApiResponse<T> {
  [key: string]: T;
}

// ---------------------- AUTO TASK TYPES ----------------------

export type AutoTaskStatus =
  | 'idle'
  | 'running'
  | 'pausing'
  | 'paused'
  | 'waiting_clarification'
  | 'completed'
  | 'error';

export interface AutoTaskHandoff {
  next_hint: string;
  signal: 'CONTINUE' | 'STOP';
}

export interface AutoTaskStep {
  id: string;
  description: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'needs_clarification';
}

export interface AutoTaskCurrent {
  id: string;
  parent_id?: string | null;
  title: string;
  objective: string;
  context_refs: string[];
  plan: AutoTaskStep[];
  workdir: string;
  tests_required: string[];
  review_checks: string[];
  status: AutoTaskStep['status'];
  handoff: AutoTaskHandoff;
  updated_at?: string | null;
}

export interface AutoTaskStatePayload {
  status: AutoTaskStatus;
  current_task: AutoTaskCurrent | null;
  thread_id?: string | null;
  attempts?: number;
  last_error?: string | null;
}

export interface AutoTaskMessage {
  id: string;
  role: 'system' | 'codex' | 'user' | 'command';
  text: string;
  kind?: string;
  timestamp?: string;
  meta?: Record<string, unknown> | null;
}

export interface AutoTaskEvent {
  type: string;
  [key: string]: unknown;
}

export interface KnowledgeUpdateItem {
  path: string;
  summary?: string;
  written?: boolean;
}

export interface AutoTaskSessionRecord {
  taskId: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'paused';
  events: AutoTaskEvent[];
  messages?: AutoTaskMessage[];
  summaryMarkdown?: string;
  knowledgeUpdates?: KnowledgeUpdateItem[];
  tests?: { command: string; status: string; details?: string }[];
  retries: number;
  startedAt?: string;
  endedAt?: string;
}

export interface AutoTaskAlert {
  id: string;
  level: 'info' | 'warning' | 'error';
  message: string;
  timestamp: string;
}

export interface AutoTaskMetrics {
  timestamp: string;
  tasks_completed: number;
  failures: number;
  total_tokens?: number;
}
