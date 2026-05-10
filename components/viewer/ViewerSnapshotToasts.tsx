"use client";

import { CircleCheck, ImageDown } from "lucide-react";
import { Button } from "@/components/ui/button";

type Props = {
  /** Clipboard succeeded — brief top confirmation with circle-check right of label (RTL). */
  copyToastVisible: boolean;
  /** PNG object URL until user downloads or clears. */
  downloadUrl: string | null;
  onDownload: () => void;
};

export function ViewerSnapshotToasts({
  copyToastVisible,
  downloadUrl,
  onDownload,
}: Props) {
  if (!copyToastVisible && !downloadUrl) return null;

  return (
    <div
      className="pointer-events-none fixed left-1/2 top-[max(0.75rem,env(safe-area-inset-top))] z-[200] flex w-[min(22rem,calc(100vw-1.5rem))] -translate-x-1/2 flex-col gap-2"
      dir="rtl"
    >
      {copyToastVisible && (
        <div className="pointer-events-auto flex items-center gap-2 rounded-xl border border-emerald-600/50 bg-zinc-950/95 px-4 py-3 text-sm font-medium text-emerald-100 shadow-lg backdrop-blur-sm">
          <CircleCheck className="h-5 w-5 shrink-0 text-emerald-400" aria-hidden />
          <span>הועתק לקליפ-בורד</span>
        </div>
      )}

      {downloadUrl && (
        <Button
          type="button"
          variant="secondary"
          className="pointer-events-auto h-auto w-full justify-center gap-2 rounded-xl border border-zinc-600 bg-zinc-900/95 py-3 text-sm font-semibold shadow-lg backdrop-blur-sm"
          onClick={onDownload}
        >
          <ImageDown className="h-5 w-5 shrink-0 text-sky-300" aria-hidden />
          שמירה כתמונה
        </Button>
      )}
    </div>
  );
}
