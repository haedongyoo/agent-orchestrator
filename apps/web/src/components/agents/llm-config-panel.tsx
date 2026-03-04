"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  useAgentLLMConfig,
  useLLMProviders,
  useLLMModels,
  useSetAgentLLMConfig,
  useTestAgentLLMConfig,
} from "@/hooks/use-llm-config";

export function LLMConfigPanel({ agentId }: { agentId: string }) {
  const { data: config, isLoading } = useAgentLLMConfig(agentId);
  const { data: providers } = useLLMProviders();
  const setConfig = useSetAgentLLMConfig(agentId);
  const testConfig = useTestAgentLLMConfig(agentId);

  const [providerId, setProviderId] = useState("");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [maxTokens, setMaxTokens] = useState("32768");
  const [temperature, setTemperature] = useState("0.7");

  const { data: models } = useLLMModels(providerId || undefined);

  // Populate from existing config
  useEffect(() => {
    if (config) {
      const parts = config.model.split("/");
      if (parts.length >= 2) {
        setProviderId(parts[0]);
        setModelId(config.model);
      }
      setApiBaseUrl(config.api_base_url || "");
      setMaxTokens(config.max_tokens.toString());
      setTemperature(config.temperature.toString());
    }
  }, [config]);

  const handleSave = () => {
    setConfig.mutate({
      model: modelId || `${providerId}/default`,
      ...(apiKey ? { api_key: apiKey } : {}),
      ...(apiBaseUrl ? { api_base_url: apiBaseUrl } : {}),
      max_tokens: parseInt(maxTokens) || 32768,
      temperature: parseFloat(temperature) || 0.7,
    });
  };

  const handleTest = () => {
    testConfig.mutate();
  };

  if (isLoading) {
    return <div className="py-4 text-sm text-[var(--muted-foreground)]">Loading LLM config...</div>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          LLM Configuration
          {config?.has_api_key && (
            <Badge variant="secondary">API key set</Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Provider</Label>
            <select
              value={providerId}
              onChange={(e) => {
                setProviderId(e.target.value);
                setModelId("");
              }}
              className="flex h-9 w-full rounded-md border border-[var(--input)] bg-transparent px-3 py-1 text-sm"
            >
              <option value="">Select provider</option>
              {providers?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>Model</Label>
            <select
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              className="flex h-9 w-full rounded-md border border-[var(--input)] bg-transparent px-3 py-1 text-sm"
              disabled={!providerId}
            >
              <option value="">Select model</option>
              {models?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-2">
          <Label>API Key</Label>
          <Input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={config?.has_api_key ? "Leave blank to keep current" : "Enter API key"}
          />
        </div>

        <div className="space-y-2">
          <Label>API Base URL (optional)</Label>
          <Input
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
            placeholder="e.g. http://ollama:11434 (for self-hosted)"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Max Tokens</Label>
            <Input
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Temperature</Label>
            <Input
              type="number"
              step="0.1"
              min="0"
              max="2"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
            />
          </div>
        </div>

        <div className="flex gap-3">
          <Button onClick={handleSave} disabled={setConfig.isPending}>
            {setConfig.isPending ? "Saving..." : "Save Config"}
          </Button>
          <Button
            variant="outline"
            onClick={handleTest}
            disabled={testConfig.isPending}
          >
            {testConfig.isPending ? "Testing..." : "Test Connection"}
          </Button>
        </div>

        {setConfig.isSuccess && (
          <p className="text-sm text-green-600">Configuration saved.</p>
        )}
        {testConfig.data && (
          <p
            className={`text-sm ${testConfig.data.success ? "text-green-600" : "text-[var(--destructive)]"}`}
          >
            {testConfig.data.message}
          </p>
        )}
        {(setConfig.error || testConfig.error) && (
          <p className="text-sm text-[var(--destructive)]">
            {(setConfig.error || testConfig.error)?.message}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
