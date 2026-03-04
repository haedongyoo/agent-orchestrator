"use client";

import { useAgentTemplates } from "@/hooks/use-agents";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { AgentTemplate } from "@/lib/types";

interface TemplatePickerProps {
  onSelect: (template: AgentTemplate) => void;
  onSkip: () => void;
}

export function TemplatePicker({ onSelect, onSkip }: TemplatePickerProps) {
  const { data: templates, isLoading } = useAgentTemplates();

  if (isLoading) {
    return <div className="py-8 text-center text-sm text-[var(--muted-foreground)]">Loading templates...</div>;
  }

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h2 className="text-lg font-semibold">Choose a template</h2>
        <p className="text-sm text-[var(--muted-foreground)]">
          Start with a pre-configured role or create from scratch
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {templates?.map((t) => (
          <Card
            key={t.id}
            className="cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => onSelect(t)}
          >
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{t.name}</CardTitle>
              <CardDescription className="line-clamp-2">{t.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1">
                {t.allowed_tools.slice(0, 4).map((tool) => (
                  <Badge key={tool} variant="secondary" className="text-xs">
                    {tool.replace(/_/g, " ")}
                  </Badge>
                ))}
                {t.allowed_tools.length > 4 && (
                  <Badge variant="secondary" className="text-xs">
                    +{t.allowed_tools.length - 4}
                  </Badge>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="text-center">
        <Button variant="ghost" onClick={onSkip}>
          Start from scratch
        </Button>
      </div>
    </div>
  );
}
