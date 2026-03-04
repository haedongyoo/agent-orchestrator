"""
Tool registry builder.

Returns a dict mapping tool_name → async callable, pre-wired with agent context.
All callables pass through the sandbox before executing.
"""
from __future__ import annotations

from agent_runtime.sandbox import Sandbox
from agent_runtime.tools.email_tool import send_email, read_email_inbox
from agent_runtime.tools.telegram_tool import send_telegram
from agent_runtime.tools.webchat_tool import post_web_message
from agent_runtime.tools.approval_tool import request_approval
from agent_runtime.tools.scheduler_tool import schedule_followup
from agent_runtime.tools.vendor_tool import upsert_vendor
from agent_runtime.tools.translate_tool import translate_message


def build_tool_registry(
    sandbox: Sandbox,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
) -> dict:
    """
    Returns a dict of {tool_name: async fn} with context pre-bound.
    Every callable is wrapped so that the sandbox check happens automatically.
    """
    ctx = dict(agent_id=agent_id, workspace_id=workspace_id, thread_id=thread_id)

    def sandboxed(name, fn):
        async def wrapper(**kwargs):
            return await sandbox.call(name, fn, **{**ctx, **kwargs})
        return wrapper

    return {
        "send_email":       sandboxed("send_email",       send_email),
        "read_email_inbox": sandboxed("read_email_inbox", read_email_inbox),
        "send_telegram":    sandboxed("send_telegram",    send_telegram),
        "post_web_message": sandboxed("post_web_message", post_web_message),
        "request_approval": sandboxed("request_approval", request_approval),
        "schedule_followup":sandboxed("schedule_followup",schedule_followup),
        "upsert_vendor":    sandboxed("upsert_vendor",    upsert_vendor),
        "translate_message":sandboxed("translate_message",translate_message),
    }


# Tool schemas in OpenAI function-calling format (LiteLLM universal format).
# LiteLLM translates these to each provider's native format automatically:
#   Anthropic  → input_schema
#   Gemini     → function declarations
#   Ollama     → depends on model's tool-use support
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email on behalf of the agent's shared inbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":          {"type": "array", "items": {"type": "string"}, "description": "Recipient email addresses"},
                    "subject":     {"type": "string"},
                    "body":        {"type": "string"},
                    "attachments": {"type": "array", "items": {"type": "object"}, "default": []},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_email_inbox",
            "description": "Read unread emails from the shared inbox for this thread.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram",
            "description": "Send a Telegram message to the user's chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":    {"type": "string"},
                    "chat_id": {"type": "string", "description": "Telegram chat_id (optional, defaults to workspace user)"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_web_message",
            "description": "Post a message to the web chat thread.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_approval",
            "description": "Request user approval for a sensitive action (e.g. contacting a new email recipient, sharing info with another agent).",
            "parameters": {
                "type": "object",
                "properties": {
                    "approval_type": {
                        "type": "string",
                        "enum": ["enable_agent_chat", "send_email", "new_recipient", "share_info", "other"],
                    },
                    "scope":  {"type": "object",  "description": "Approval scope details (agents, recipients, duration)"},
                    "reason": {"type": "string",  "description": "Human-readable explanation for the request"},
                },
                "required": ["approval_type", "scope", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_followup",
            "description": "Schedule a future follow-up action (e.g. re-ping a supplier after 24h if no reply).",
            "parameters": {
                "type": "object",
                "properties": {
                    "delay_seconds": {"type": "integer", "description": "Seconds from now to trigger the follow-up"},
                    "message":       {"type": "string",  "description": "Follow-up instruction or message"},
                },
                "required": ["delay_seconds", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upsert_vendor",
            "description": "Create or update a vendor/contractor profile in the workspace CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name":     {"type": "string"},
                    "email":    {"type": "string"},
                    "category": {"type": "string", "description": "e.g. furniture_supplier, material_factory, contractor"},
                    "notes":    {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "translate_message",
            "description": "Translate text into another language. Useful for understanding inbound foreign-language messages and composing outbound replies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":            {"type": "string", "description": "The text to translate"},
                    "target_language": {"type": "string", "description": "Language to translate into (e.g. 'Chinese', 'Spanish', 'Korean')"},
                    "source_language": {"type": "string", "description": "Source language (default: auto-detect)", "default": "auto"},
                },
                "required": ["text", "target_language"],
            },
        },
    },
]
