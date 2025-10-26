export const modelOptions = [
  { value: 'gpt-5-codex', label: 'gpt-5-codex' },
  { value: 'gpt-5', label: 'gpt-5' },
  { value: 'o4-mini', label: 'o4-mini' },
  { value: 'o3-mini', label: 'o3-mini' },
];

export const reasoningOptions = [
  { value: 'minimal', label: '极低' },
  { value: 'low', label: '较低' },
  { value: 'medium', label: '标准' },
  { value: 'high', label: '高' },
];

export const summaryOptions = [
  { value: 'auto', label: '自动' },
  { value: 'concise', label: '简洁' },
  { value: 'detailed', label: '详细' },
  { value: 'none', label: '关闭' },
];

export const approvalOptions = [
  { value: 'on-request', label: '按需审批' },
  { value: 'on-failure', label: '失败时审批' },
  { value: 'untrusted', label: '严格审批' },
  { value: 'never', label: '无需审批' },
];

export const sandboxOptions = [
  { value: 'workspace-write', label: '工作区写入' },
  { value: 'read-only', label: '只读' },
  { value: 'danger-full-access', label: '完全开放' },
];
