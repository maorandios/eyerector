"use client";

import { CircleCheck } from "lucide-react";

type Props = {
  /** Clipboard succeeded — brief top confirmation with circle-check right of label (RTL). */
  copyToastVisible: boolean;
};

export function ViewerSnapshotToasts({ copyToastVisible }: Props) {
  if (!copyToastVisible) return null;

  return (
    <div
      className="pointer-events-none fixed left-1/2 top-[max(0.75rem,env(safe-area-inset-top))] z-[200] flex -translate-x-1/2"
      dir="rtl"
    >
      <div className="pointer-events-auto inline-flex items-center gap-2 rounded-full border border-emerald-500/25 bg-white/95 px-3.5 py-2 text-sm font-semibold text-zinc-800 shadow-[0_10px_30px_rgba(39,39,42,0.16)] ring-1 ring-black/5 backdrop-blur-md">
        <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/12">
          <CircleCheck className="size-3.5 text-emerald-600" aria-hidden />
        </span>
        <span className="whitespace-nowrap">התמונה הועתקה</span>
      </div>
    </div>
  );
}
