export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export const VALID_TOOLS = [
  "send_email",
  "read_email_inbox",
  "send_telegram",
  "post_web_message",
  "request_approval",
  "upsert_vendor",
  "schedule_followup",
  "translate_message",
] as const;

export const VALID_CHANNELS = ["web", "telegram", "email", "system"] as const;

export const APPROVAL_TYPES = [
  "enable_agent_chat",
  "send_email",
  "new_recipient",
  "share_info",
  "commitment_detected",
  "payment_detected",
  "scope_change_detected",
  "other",
] as const;

export const TASK_STATUSES = [
  "queued",
  "running",
  "blocked",
  "needs_approval",
  "done",
  "failed",
] as const;

export const SSO_PROVIDERS = ["google", "github", "microsoft"] as const;
