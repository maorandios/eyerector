"use client";

import { useMemo } from "react";
import { gridStationsFromEdited } from "@/lib/plan-crop/types";
import type { CropRectNorm, RegionStructuralAnalysis } from "@/lib/plan-crop/types";
import { he } from "@/lib/i18n/he";

type RegionGridOverlayProps = {
  imageUrl: string;
  cropRect: CropRectNorm;
  analysis: RegionStructuralAnalysis;
  editedParameters: Record<string, string | number | boolean | string[]>;
};

/** Preview grid lines inside the crop box only (plan +Y up, image +Y down). */
export function RegionGridOverlay({
  imageUrl,
  cropRect,
  analysis,
  editedParameters,
}: RegionGridOverlayProps) {
  const { xs, ys } = useMemo(
    () => gridStationsFromEdited(editedParameters, analysis),
    [editedParameters, analysis],
  );

  const xRange = useMemo(() => {
    if (xs.length < 2) return { min: 0, max: 0 };
    return { min: xs[0], max: xs[xs.length - 1] };
  }, [xs]);

  const yRange = useMemo(() => {
    if (ys.length < 2) return { min: 0, max: 0 };
    return { min: ys[0], max: ys[ys.length - 1] };
  }, [ys]);

  const verticalLines = useMemo(() => {
    const span = xRange.max - xRange.min;
    if (span <= 0 || xs.length < 2) return [];
    return xs.map((station, i) => ({
      id: `gx-${i}`,
      leftPct: (station - xRange.min) / span,
    }));
  }, [xs, xRange]);

  const horizontalLines = useMemo(() => {
    const span = yRange.max - yRange.min;
    if (span <= 0 || ys.length < 2) return [];
    return ys.map((station, i) => ({
      id: `gy-${i}`,
      topPct: 1 - (station - yRange.min) / span,
    }));
  }, [ys, yRange]);

  if (verticalLines.length < 2 && horizontalLines.length < 2) {
    return (
      <p className="text-xs text-amber-300">
        {he.planCropGridPreviewMissing}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-slate-400">
        {he.planCropGridPreviewHint} — X: {xs.length} · Y: {ys.length}
        {xRange.max > 0 ? ` · span ${Math.round(xRange.max)} mm` : ""}
      </p>
      <div className="relative max-h-[40vh] w-full overflow-hidden rounded-lg border border-slate-700 bg-slate-900">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl}
          alt={he.planCropCanvasAlt}
          className="block h-auto max-h-[40vh] w-full object-contain"
          draggable={false}
        />
        <div
          className="pointer-events-none absolute border-2 border-[#00ffcc]/80"
          style={{
            left: `${cropRect.x * 100}%`,
            top: `${cropRect.y * 100}%`,
            width: `${cropRect.w * 100}%`,
            height: `${cropRect.h * 100}%`,
          }}
        >
          {verticalLines.map((line) => (
            <div
              key={line.id}
              className="absolute bottom-0 top-0 w-px bg-orange-400/90"
              style={{ left: `${line.leftPct * 100}%` }}
            />
          ))}
          {horizontalLines.map((line) => (
            <div
              key={line.id}
              className="absolute left-0 right-0 h-px bg-sky-400/90"
              style={{ top: `${line.topPct * 100}%` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
