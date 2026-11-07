import { Bot, Database, Send, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useApi } from "../hooks/useApi";
import { api, ApiError, post } from "../services/api";
import type { AssistantStatus, ChatMessage, Conversation } from "../types";
import { Button, ErrorNote } from "./ui";

const PROJECT_PROMPTS = [
  "Can you summarise this inspection?",
  "What objects were detected?",
  "Which areas require further inspection?",
  "Which findings have not been reviewed?",
  "Can you prepare an inspection report?",
];
const COMPARISON_PROMPTS = ["What is the difference between these two images?", "Can you summarise this comparison?"];

interface Props {
  projectId?: string;
  comparisonId?: string;
  workspaceId?: string;
}

export function Assistant({ projectId, comparisonId, workspaceId }: Props) {
  const status = useApi<AssistantStatus>("/assistant/status");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const log = useRef<HTMLDivElement>(null);
  const prompts = comparisonId ? COMPARISON_PROMPTS : PROJECT_PROMPTS;

  useEffect(() => {
    let cancelled = false;
    setConversation(null);
    setMessages([]);
    const load = async () => {
      if (projectId) {
        const existing = await api<Conversation[]>(`/assistant/conversations?project_id=${projectId}`);
        if (existing.length && !cancelled) {
          const full = await api<Conversation>(`/assistant/conversations/${existing[0].id}`);
          if (!cancelled) {
            setConversation(full);
            setMessages(full.messages);
          }
        }
      }
    };
    load().catch(() => undefined);
    return () => { cancelled = true; };
  }, [projectId, comparisonId]);

  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }); }, [messages, busy]);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || busy) return;
    setBusy(true);
    setError(null);
    setDraft("");
    const optimistic: ChatMessage = { id: `local-${Date.now()}`, role: "user", content, source: "user", created_at: new Date().toISOString() };
    setMessages((all) => [...all, optimistic]);
    try {
      const current = conversation ?? await post<Conversation>("/assistant/conversations", {
        project_id: projectId ?? null, comparison_id: comparisonId ?? null, workspace_id: workspaceId ?? null,
      });
      setConversation(current);
      const suffix = workspaceId ? `?workspace_id=${workspaceId}` : "";
      const reply = await post<ChatMessage>(`/assistant/conversations/${current.id}/messages${suffix}`, { content });
      setMessages((all) => [...all, reply]);
      void status.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The question could not be sent.");
      setDraft(content);
      setMessages((all) => all.filter((m) => m.id !== optimistic.id));
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void send(draft);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-start gap-2 border-b border-ink-700 px-3 py-2 text-xs text-text-3">
        {status.data?.external_ai_enabled ? <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" /> : <Database className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />}
        <span>{status.data?.message ?? "Checking assistant status"}</span>
      </div>
      <div ref={log} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3" aria-live="polite">
        {messages.length === 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-text-2"><Bot className="h-4 w-4" />Ask about these records</div>
            <div className="flex flex-col items-start gap-1.5">
              {prompts.map((prompt) => (
                <button key={prompt} type="button" onClick={() => void send(prompt)}
                  className="rounded-md border border-ink-600 px-2 py-1 text-left text-xs text-text-2 hover:border-accent/60 hover:text-text-1">{prompt}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message) => (
          <div key={message.id} className={message.role === "user" ? "ml-6 rounded-lg bg-accent-dim/60 px-3 py-2" : "mr-2 rounded-lg bg-ink-800 px-3 py-2"}>
            <p className="whitespace-pre-wrap break-words text-[13px] leading-relaxed text-text-1">{message.content}</p>
            {message.role === "assistant" && <p className="mt-1 text-[10px] uppercase tracking-wide text-text-3">{message.source === "records" ? "From stored records" : `Written by ${message.source}`}</p>}
          </div>
        ))}
        {busy && <p className="px-1 text-xs text-text-3">Reading the records...</p>}
        {error && <ErrorNote message={error} />}
      </div>
      <form onSubmit={onSubmit} className="flex gap-2 border-t border-ink-700 p-2">
        <input aria-label="Question" className="field" maxLength={2000} placeholder="Ask about this inspection" value={draft} onChange={(e) => setDraft(e.target.value)} />
        <Button type="submit" variant="primary" icon={Send} aria-label="Send" disabled={!draft.trim()} busy={busy} />
      </form>
    </div>
  );
}
