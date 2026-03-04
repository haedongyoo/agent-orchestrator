"use client";

import { useState } from "react";
import { useCreateAgent } from "@/hooks/use-agents";
import { AgentForm } from "@/components/agents/agent-form";
import { TemplatePicker } from "@/components/agents/template-picker";
import type { AgentCreate, AgentTemplate } from "@/lib/types";

export default function NewAgentPage() {
  const createAgent = useCreateAgent();
  const [step, setStep] = useState<"pick" | "form">("pick");
  const [initial, setInitial] = useState<Partial<AgentCreate>>({});

  const handleTemplateSelect = (template: AgentTemplate) => {
    setInitial({
      name: "",
      role_prompt: template.role_prompt,
      allowed_tools: template.allowed_tools,
      rate_limit_per_min: template.rate_limit_per_min,
      max_concurrency: template.max_concurrency,
    });
    setStep("form");
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">New Agent</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          {step === "pick"
            ? "Choose a template to get started quickly"
            : "Configure your agent"}
        </p>
      </div>

      {step === "pick" ? (
        <TemplatePicker
          onSelect={handleTemplateSelect}
          onSkip={() => setStep("form")}
        />
      ) : (
        <AgentForm
          mode="create"
          initial={initial}
          onSubmit={(data) => createAgent.mutateAsync(data as AgentCreate)}
        />
      )}
    </div>
  );
}
