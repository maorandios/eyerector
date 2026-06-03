"use client";

import { Bot, User } from "lucide-react";
import type { ChatMessage } from "./types";
import { cn } from "@/lib/utils";

interface AiChatMessageProps {
  message: ChatMessage;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString("he-IL", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AiChatMessage({ message }: AiChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex w-full gap-2.5",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      <div
        className={cn(
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
          isUser
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
            : "border-cyan-500/30 bg-cyan-500/10 text-cyan-400",
        )}
        aria-hidden
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      <div
        className={cn(
          "flex max-w-[85%] flex-col gap-1",
          isUser ? "items-end" : "items-start",
        )}
      >
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
            isUser
              ? "rounded-te-2xl rounded-ts-md bg-emerald-600/20 text-slate-100 ring-1 ring-emerald-500/25"
              : "rounded-ts-2xl rounded-te-md bg-slate-800/90 text-slate-200 ring-1 ring-slate-700/80",
          )}
        >
          {message.text}
        </div>
        <time
          dateTime={message.timestamp.toISOString()}
          suppressHydrationWarning
          className="px-1 text-[10px] tabular-nums text-slate-500"
        >
          {formatTime(message.timestamp)}
        </time>
      </div>
    </div>
  );
}
