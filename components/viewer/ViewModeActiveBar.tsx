"use client";

import { Button } from "@/components/ui/button";
import { VIEW_MODE_LABELS_HE, type ViewModeId } from "@/lib/viewer/view-mode-presets";

interface Props {
  viewMode: ViewModeId;
  onExit: () => void;
  /** When clipping HUD is open, sit above it so both stay visible. */
  liftAboveClippingHud?: boolean;
}

export function ViewModeActiveBar({ viewMode, onExit, liftAboveClippingHud = false }: Props) {
  const label = VIEW_MODE_LABELS_HE[viewMode];
  return (
    <div
      className={
        liftAboveClippingHud
          ? "pointer-events-auto absolute bottom-[calc(12.5rem+env(safe-area-inset-bottom))] left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-zinc-600 bg-zinc-950/95 px-3 py-2 shadow-xl backdrop-blur-sm"
          : "pointer-events-auto absolute bottom-[max(5rem,calc(5rem+env(safe-area-inset-bottom)))] left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-zinc-600 bg-zinc-950/95 px-3 py-2 shadow-xl backdrop-blur-sm"
      }
      dir="rtl"
    >
      <span className="text-sm font-medium text-zinc-100">
        מבט: <span className="text-blue-200">{label}</span>
      </span>
      <Button
        type="button"
        variant="secondary"
        className="h-8 px-3 text-xs font-semibold"
        onClick={onExit}
      >
        בטל מבט
      </Button>
    </div>
  );
}
