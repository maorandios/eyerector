"use client";

import { Loader2 } from "lucide-react";
import { he } from "@/lib/i18n/he";
import { cn } from "@/lib/utils";

interface AiLoadingOverlayProps {
  visible: boolean;
  className?: string;
}

export function AiLoadingOverlay({ visible, className }: AiLoadingOverlayProps) {
  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={cn(
        "absolute inset-0 z-20 flex items-center justify-center",
        "bg-slate-950/55 backdrop-blur-md",
        className,
      )}
    >
      <div className="mx-4 flex max-w-sm flex-col items-center gap-4 rounded-2xl border border-slate-700/80 bg-slate-900/70 px-8 py-10 text-center shadow-2xl shadow-cyan-950/30">
        <div className="relative">
          <div className="absolute inset-0 animate-ping rounded-full bg-cyan-500/20" />
          <div className="relative flex h-14 w-14 items-center justify-center rounded-full border border-cyan-500/40 bg-cyan-500/10">
            <Loader2 className="h-7 w-7 animate-spin text-cyan-400" aria-hidden />
          </div>
        </div>
        <div className="space-y-1">
          <p className="text-base font-semibold text-slate-100">{he.aiDesignerLoadingTitle}</p>
          <p className="text-sm text-slate-400">{he.aiDesignerLoadingSubtitle}</p>
        </div>
      </div>
    </div>
  );
}
