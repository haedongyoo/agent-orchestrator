// ── Auth ──────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  is_active: boolean;
  sso_provider: string | null;
}

// ── Workspace ────────────────────────────────────────────────────────────────

export interface Workspace {
  id: string;
  name: string;
  timezone: string;
  language_pref: string;
}

export interface WorkspaceCreate {
  name: string;
  timezone?: string;
  language_pref?: string;
}

export interface WorkspaceUpdate {
  name?: string;
  timezone?: string;
  language_pref?: string;
}

// ── Shared Email ─────────────────────────────────────────────────────────────

export interface SharedEmailAccount {
  id: string;
  workspace_id: string;
  provider_type: string;
  from_alias: string;
  signature_template: string | null;
  is_active: boolean;
}

export interface SharedEmailCreate {
  provider_type: string;
  credentials_ref: string;
  from_alias: string;
  signature_template?: string;
}

// ── Agent ────────────────────────────────────────────────────────────────────

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  role_prompt: string;
  allowed_tools: string[];
  is_enabled: boolean;
  rate_limit_per_min: number;
  max_concurrency: number;
  created_at: string;
  updated_at: string;
}

export interface AgentCreate {
  name: string;
  role_prompt: string;
  allowed_tools: string[];
  telegram_bot_token_ref?: string;
  is_enabled?: boolean;
  rate_limit_per_min?: number;
  max_concurrency?: number;
}

export interface AgentUpdate {
  name?: string;
  role_prompt?: string;
  allowed_tools?: string[];
  telegram_bot_token_ref?: string;
  is_enabled?: boolean;
  rate_limit_per_min?: number;
  max_concurrency?: number;
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  role_prompt: string;
  allowed_tools: string[];
  rate_limit_per_min: number;
  max_concurrency: number;
}

// ── Thread ───────────────────────────────────────────────────────────────────

export interface Thread {
  id: string;
  workspace_id: string;
  title: string;
  status: string;
}

export interface ThreadCreate {
  title: string;
}

// ── Message ──────────────────────────────────────────────────────────────────

export interface Message {
  id: string;
  thread_id: string;
  sender_type: string;
  sender_id: string | null;
  channel: string;
  content: string;
  created_at: string;
}

export interface MessageCreate {
  content: string;
  channel?: string;
}

export interface MessagePage {
  items: Message[];
  next_cursor: string | null;
}

// ── Task ─────────────────────────────────────────────────────────────────────

export interface Task {
  id: string;
  workspace_id: string;
  thread_id: string;
  objective: string;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface TaskStep {
  id: string;
  task_id: string;
  agent_id: string;
  step_type: string;
  tool_call: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  status: string;
  created_at: string;
  updated_at: string;
}

// ── Approval ─────────────────────────────────────────────────────────────────

export interface Approval {
  id: string;
  workspace_id: string;
  approval_type: string;
  requested_by: string;
  scope: Record<string, unknown>;
  status: string;
  reason: string | null;
}

// ── Vendor ───────────────────────────────────────────────────────────────────

export interface Vendor {
  id: string;
  workspace_id: string;
  name: string;
  email: string | null;
  category: string;
  contact_name: string | null;
  phone: string | null;
  website: string | null;
  country: string | null;
  notes: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface VendorCreate {
  name: string;
  email?: string;
  category: string;
  contact_name?: string;
  phone?: string;
  website?: string;
  country?: string;
  notes?: string;
  tags?: string[];
}
