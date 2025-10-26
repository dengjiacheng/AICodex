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

export interface SessionRoleInfo {
  id: string;
  name: string;
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
  sessions: Session[];
}

export interface ApiResponse<T> {
  [key: string]: T;
}
