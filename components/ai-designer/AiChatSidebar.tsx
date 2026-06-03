"use client";

import { useEffect, useRef } from "react";
import { Download, FileSpreadsheet, Sparkles, Wifi } from "lucide-react";
import { he } from "@/lib/i18n/he";
import { AiChatInput } from "./AiChatInput";
import { AiChatMessage } from "./AiChatMessage";
import type { ChatMessage } from "./types";
import { cn } from "@/lib/utils";

interface AiChatSidebarProps {
  messages: ChatMessage[];
  inputValue: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  isProcessing?: boolean;
  className?: string;
}

export function AiChatSidebar({
  messages,
  inputValue,
  onInputChange,
  onSend,
  isProcessing = false,
  className,
}: AiChatSidebarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 w-full flex-col",
        "border-slate-800 bg-slate-900 lg:w-[30%] lg:min-w-[280px] lg:max-w-[420px] lg:border-e",
        className,
      )}
    >
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 px-4 py-3.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500/20 to-emerald-500/20 ring-1 ring-cyan-500/30">
            <Sparkles className="h-4 w-4 text-cyan-400" aria-hidden />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold text-slate-100">
              {he.aiDesignerTitle}
            </h1>
            <p className="text-[11px] text-slate-500">Chat-to-BIM</p>
          </div>
        </div>
        <div
          className="flex shrink-0 items-center gap-1.5 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1"
          title={he.aiDesignerConnected}
        >
          <Wifi className="h-3 w-3 text-emerald-400" aria-hidden />
          <span className="text-[10px] font-medium text-emerald-400">
            {he.aiDesignerConnected}
          </span>
        </div>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 space-y-4 overflow-y-auto overscroll-contain px-3 py-4"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
      >
        {messages.map((msg) => (
          <AiChatMessage key={msg.id} message={msg} />
        ))}
      </div>

      <AiChatInput
        value={inputValue}
        onChange={onInputChange}
          onSend={onSend}
        disabled={isProcessing}
      />

      <footer className="grid shrink-0 grid-cols-2 gap-2 border-t border-slate-800 p-3">
        <button
          type="button"
          disabled
          title={`${he.aiDesignerDownloadIfc} (${he.aiDesignerComingSoon})`}
          className={cn(
            "flex items-center justify-center gap-2 rounded-xl border border-slate-700",
            "bg-slate-800/50 px-3 py-2.5 text-xs font-medium text-slate-500",
            "cursor-not-allowed opacity-60",
          )}
        >
          <Download className="h-4 w-4 shrink-0" aria-hidden />
          <span className="truncate">{he.aiDesignerDownloadIfc}</span>
        </button>
        <button
          type="button"
          disabled
          title={`${he.aiDesignerExportExcel} (${he.aiDesignerComingSoon})`}
          className={cn(
            "flex items-center justify-center gap-2 rounded-xl border border-slate-700",
            "bg-slate-800/50 px-3 py-2.5 text-xs font-medium text-slate-500",
            "cursor-not-allowed opacity-60",
          )}
        >
          <FileSpreadsheet className="h-4 w-4 shrink-0" aria-hidden />
          <span className="truncate">{he.aiDesignerExportExcel}</span>
        </button>
      </footer>
    </aside>
  );
}
