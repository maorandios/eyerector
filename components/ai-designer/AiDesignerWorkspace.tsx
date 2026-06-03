"use client";

import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import { AiChatSidebar } from "./AiChatSidebar";
import { AiDesignerViewport } from "./AiDesignerViewport";
import { AiLoadingOverlay } from "./AiLoadingOverlay";
import { INITIAL_CHAT_MESSAGES } from "./placeholder-messages";
import type { ChatMessage, ChatToIfcHistoryMessage } from "./types";
import { he } from "@/lib/i18n/he";
import { ChatToIfcError, fetchChatToIfc } from "@/lib/ai-designer/chat-to-ifc-client";
import { createIfcObjectUrl, loadIfcBlobIntoViewer } from "@/lib/ai-designer/load-ifc-blob";
import { IfcLoadError } from "@/lib/viewer/ifc-loader";
import type { ViewerEngine } from "@/lib/viewer/engine";

function createMessageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function toApiHistory(messages: ChatMessage[]): ChatToIfcHistoryMessage[] {
  return messages.map((m) => ({ role: m.role, text: m.text }));
}

export function AiDesignerWorkspace() {
  const engineRef = useRef<ViewerEngine | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_CHAT_MESSAGES);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [hasModel, setHasModel] = useState(false);

  const handleEngineReady = useCallback((engine: ViewerEngine | null) => {
    engineRef.current = engine;
  }, []);

  const appendAiMessage = useCallback((text: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: createMessageId(),
        role: "ai",
        text,
        timestamp: new Date(),
      },
    ]);
  }, []);

  const handleSendMessage = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMessage: ChatMessage = {
      id: createMessageId(),
      role: "user",
      text: trimmed,
      timestamp: new Date(),
    };

    const historyForApi = toApiHistory([...messages, userMessage]);

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    let objectUrl: string | undefined;

    try {
      const { blob: ifcBlob, specSummary } = await fetchChatToIfc({
        prompt: trimmed,
        history: historyForApi,
      });

      objectUrl = createIfcObjectUrl(ifcBlob);

      const engine = engineRef.current;
      if (!engine) {
        throw new Error(he.aiDesignerViewerNotReady);
      }

      await loadIfcBlobIntoViewer(engine, ifcBlob, objectUrl);
      objectUrl = undefined;

      setHasModel(true);
      appendAiMessage(
        specSummary
          ? `${he.aiDesignerModelReady}\n\n${he.aiDesignerBuiltAs}: ${specSummary}`
          : he.aiDesignerModelReady,
      );
    } catch (err) {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }

      let errorText = he.aiDesignerRequestFailed;
      if (err instanceof ChatToIfcError) {
        errorText = err.message;
      } else if (err instanceof IfcLoadError) {
        errorText = err.message;
      } else if (err instanceof Error && err.message) {
        errorText = err.message;
      }

      appendAiMessage(`${he.aiDesignerErrorPrefix} ${errorText}`);
    } finally {
      setIsLoading(false);
    }
  }, [appendAiMessage, input, isLoading, messages]);

  return (
    <div className="flex h-dvh min-h-0 flex-col bg-zinc-950 text-slate-100">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/80 px-4 py-2.5 safe-top">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
        >
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          {he.aiDesignerBackHome}
        </Link>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Sparkles className="h-3.5 w-3.5 text-cyan-400" aria-hidden />
          <span className="hidden sm:inline">eyesteel · AI Structural Designer</span>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <AiChatSidebar
          messages={messages}
          inputValue={input}
          onInputChange={setInput}
          onSend={() => void handleSendMessage()}
          isProcessing={isLoading}
          className="max-h-[45vh] lg:max-h-none"
        />

        <section className="relative min-h-0 flex-1">
          <AiDesignerViewport
            hasModel={hasModel}
            onEngineReady={handleEngineReady}
            className="h-full min-h-[55vh] lg:min-h-0"
          />
          <AiLoadingOverlay visible={isLoading} />
        </section>
      </div>
    </div>
  );
}
