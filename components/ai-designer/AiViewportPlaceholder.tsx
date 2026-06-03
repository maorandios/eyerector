"use client";

import { Box, Layers3 } from "lucide-react";
import { he } from "@/lib/i18n/he";
import { cn } from "@/lib/utils";

interface AiViewportPlaceholderProps {
  className?: string;
  message?: string;
}

export function AiViewportPlaceholder({ className, message }: AiViewportPlaceholderProps) {
  return (
    <div
      className={cn(
        "relative h-full min-h-[280px] w-full overflow-hidden bg-zinc-950",
        className,
      )}
      aria-label="3D viewport"
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          backgroundImage: `
            linear-gradient(rgba(34, 211, 238, 0.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(34, 211, 238, 0.06) 1px, transparent 1px)
          `,
          backgroundSize: "48px 48px",
        }}
      />
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 80% 60% at 50% 50%, rgba(6, 182, 212, 0.08) 0%, transparent 70%)",
        }}
      />

      <div className="absolute inset-x-0 top-0 flex items-center justify-between border-b border-slate-800/80 bg-slate-900/40 px-4 py-2.5 backdrop-blur-sm">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Layers3 className="h-3.5 w-3.5 text-cyan-500/80" aria-hidden />
          <span>IFC Viewport</span>
        </div>
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-700" />
          <span className="h-2.5 w-2.5 rounded-full bg-slate-700" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/80" />
        </div>
      </div>

      <div className="flex h-full flex-col items-center justify-center gap-5 px-6 pt-10 text-center">
        <div className="relative">
          <div className="absolute -inset-4 rounded-full bg-cyan-500/5 blur-xl" />
          <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl border border-slate-700 bg-slate-900/80 shadow-lg shadow-black/40">
            <Box className="h-10 w-10 text-slate-600" strokeWidth={1.25} aria-hidden />
          </div>
        </div>
        <p className="max-w-md text-sm leading-relaxed text-slate-400">
          {message ?? he.aiDesignerViewportWaiting}
        </p>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-500" />
          <span>ViewerCanvas · בקרוב</span>
        </div>
      </div>
    </div>
  );
}
