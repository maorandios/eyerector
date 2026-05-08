"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import type { ViewerClippingUiSnapshot } from "@/lib/viewer/clipping-presets";
import { useClippingStore } from "@/lib/state/clipping-store";

type Props = {
  snapshot: ViewerClippingUiSnapshot;
  onDepthChange: (value: number) => void;
  onFlip: () => void;
  onSectionViewToggle: () => void;
  onCancel: () => void;
};

export function ClippingActiveBar({
  snapshot,
  onDepthChange,
  onFlip,
  onSectionViewToggle,
  onCancel,
}: Props) {
  const clipSectionOrthoActive = useClippingStore((s) => s.clipSectionOrthoActive);

  const step = useMemo(() => {
    const span = snapshot.depthMax - snapshot.depthMin;
    if (!(span > 0)) return 0.01;
    return Math.max(span / 256, 1e-4);
  }, [snapshot.depthMax, snapshot.depthMin]);

  if (!snapshot.active || !snapshot.labelHe) return null;

  return (
    <div
      className="pointer-events-auto absolute inset-x-0 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-[52] flex justify-center px-3 sm:bottom-[calc(5.25rem+env(safe-area-inset-bottom))]"
      dir="rtl"
    >
      <div className="flex w-full max-w-md flex-col gap-3 rounded-2xl border border-zinc-600 bg-zinc-950/96 px-4 py-3 shadow-2xl backdrop-blur-sm">
        <p className="text-center text-sm font-semibold text-zinc-100">
          קליפינג: {snapshot.labelHe}
          {snapshot.flipped ? " · הפוך" : ""}
        </p>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-zinc-400">עומק חתך</label>
          <input
            type="range"
            className="h-11 w-full cursor-pointer touch-manipulation accent-blue-500"
            min={snapshot.depthMin}
            max={snapshot.depthMax}
            step={step}
            value={snapshot.depthOffset}
            onChange={(e) => onDepthChange(Number(e.target.value))}
            aria-valuemin={snapshot.depthMin}
            aria-valuemax={snapshot.depthMax}
            aria-valuenow={snapshot.depthOffset}
          />
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button
            type="button"
            variant={clipSectionOrthoActive ? "secondary" : "default"}
            className="min-h-11 flex-1 px-4 text-sm font-semibold"
            onClick={onSectionViewToggle}
          >
            {clipSectionOrthoActive ? "ביטול חתך" : "הצג כחתך"}
          </Button>
          <Button type="button" variant="secondary" className="min-h-11 flex-1 px-4 text-sm" onClick={onFlip}>
            הפוך כיוון
          </Button>
          <Button type="button" variant="secondary" className="min-h-11 flex-1 px-4 text-sm text-red-200" onClick={onCancel}>
            בטל קליפינג
          </Button>
        </div>
      </div>
    </div>
  );
}
