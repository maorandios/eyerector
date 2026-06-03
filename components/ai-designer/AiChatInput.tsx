"use client";

import type { KeyboardEvent } from "react";
import { Mic, Send } from "lucide-react";
import { he } from "@/lib/i18n/he";
import { cn } from "@/lib/utils";

interface AiChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  className?: string;
}

export function AiChatInput({
  value,
  onChange,
  onSend,
  disabled = false,
  className,
}: AiChatInputProps) {
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className={cn("border-t border-slate-800 bg-slate-900/60 p-3", className)}>
      <div className="flex items-end gap-2">
        <button
          type="button"
          disabled
          title={`${he.aiDesignerMic} (${he.aiDesignerComingSoon})`}
          aria-label={`${he.aiDesignerMic} — ${he.aiDesignerComingSoon}`}
          className={cn(
            "flex h-12 w-12 shrink-0 items-center justify-center rounded-xl",
            "border border-slate-700 bg-slate-800/80 text-slate-400",
            "cursor-not-allowed opacity-60",
          )}
        >
          <Mic className="h-5 w-5" aria-hidden />
        </button>

        <label className="sr-only" htmlFor="ai-designer-prompt">
          {he.aiDesignerInputPlaceholder}
        </label>
        <textarea
          id="ai-designer-prompt"
          rows={2}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={he.aiDesignerInputPlaceholder}
          className={cn(
            "min-h-[48px] flex-1 resize-none rounded-xl border border-slate-700",
            "bg-slate-950/80 px-3.5 py-2.5 text-sm text-slate-100 placeholder:text-slate-500",
            "outline-none transition focus:border-cyan-500/60 focus:ring-2 focus:ring-cyan-500/20",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        />

        <button
          type="button"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          aria-label={he.aiDesignerSend}
          className={cn(
            "flex h-12 w-12 shrink-0 items-center justify-center rounded-xl",
            "bg-cyan-600 text-white transition hover:bg-cyan-500",
            "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400",
            "disabled:cursor-not-allowed disabled:opacity-40",
          )}
        >
          <Send className="h-5 w-5" aria-hidden />
        </button>
      </div>
    </div>
  );
}
