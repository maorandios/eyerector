"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Minus, Plus, RotateCcw, Undo2 } from "lucide-react";
import type { ColumnClick, RegionCropCalibrationResult } from "@/lib/plan-crop/types";
import { he } from "@/lib/i18n/he";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const HIT_RADIUS_PX = 22;
const PAN_THRESHOLD_PX = 6;
const MIN_SCALE = 0.2;
const MAX_SCALE = 8;
const ZOOM_STEP = 1.15;

type ColumnClickEditorProps = {
  cropImageUrl: string;
  calibration: RegionCropCalibrationResult;
  clicks: ColumnClick[];
  onAddClick: (click: ColumnClick) => void;
  onRemoveClick: (id: string) => void;
  onUndoLast: () => void;
  className?: string;
};

/** Map screen coords → SVG viewBox (works with CSS transform/zoom). */
function clientToSvgCoords(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
  cropW: number,
  cropH: number,
): { x: number; y: number } {
  const rect = svg.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) {
    return { x: 0, y: 0 };
  }
  return {
    x: ((clientX - rect.left) / rect.width) * cropW,
    y: ((clientY - rect.top) / rect.height) * cropH,
  };
}

function findClickNear(
  clicks: ColumnClick[],
  x: number,
  y: number,
  radius: number,
): ColumnClick | null {
  const r2 = radius * radius;
  let best: ColumnClick | null = null;
  let bestD = r2;
  for (const c of clicks) {
    const d = (c.x_px - x) ** 2 + (c.y_px - y) ** 2;
    if (d <= bestD) {
      bestD = d;
      best = c;
    }
  }
  return best;
}

export function ColumnClickEditor({
  cropImageUrl,
  calibration,
  clicks,
  onAddClick,
  onRemoveClick,
  onUndoLast,
  className,
}: ColumnClickEditorProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const pointerRef = useRef({
    down: false,
    panning: false,
    startX: 0,
    startY: 0,
    panX: 0,
    panY: 0,
    pointerId: -1,
  });
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  const cropW = calibration.crop_width_px;
  const cropH = calibration.crop_height_px;
  const aspect = `${cropW} / ${cropH}`;

  const clampScale = useCallback((s: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s)), []);

  const zoomAt = useCallback(
    (clientX: number, clientY: number, factor: number) => {
      const vp = viewportRef.current;
      if (!vp) return;
      const rect = vp.getBoundingClientRect();
      const mx = clientX - rect.left;
      const my = clientY - rect.top;
      setScale((prev) => {
        const next = clampScale(prev * factor);
        const ratio = next / prev;
        setPan((p) => ({
          x: mx - (mx - p.x) * ratio,
          y: my - (my - p.y) * ratio,
        }));
        return next;
      });
    },
    [clampScale],
  );

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const placeOrRemoveColumn = useCallback(
    (clientX: number, clientY: number) => {
      const svg = svgRef.current;
      if (!svg) return;
      const pt = clientToSvgCoords(svg, clientX, clientY, cropW, cropH);
      const hit = findClickNear(clicks, pt.x, pt.y, HIT_RADIUS_PX);
      if (hit) {
        onRemoveClick(hit.id);
        return;
      }
      onAddClick({
        id: crypto.randomUUID(),
        x_px: Math.max(0, Math.min(cropW, pt.x)),
        y_px: Math.max(0, Math.min(cropH, pt.y)),
      });
    },
    [clicks, cropH, cropW, onAddClick, onRemoveClick],
  );

  const onSvgPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      pointerRef.current = {
        down: true,
        panning: false,
        startX: e.clientX,
        startY: e.clientY,
        panX: pan.x,
        panY: pan.y,
        pointerId: e.pointerId,
      };
      (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId);
    },
    [pan.x, pan.y],
  );

  const onSvgPointerMove = useCallback((e: React.PointerEvent) => {
    const st = pointerRef.current;
    if (!st.down || e.pointerId !== st.pointerId) return;
    const dx = e.clientX - st.startX;
    const dy = e.clientY - st.startY;
    if (!st.panning && Math.hypot(dx, dy) < PAN_THRESHOLD_PX) return;
    st.panning = true;
    setPan({
      x: st.panX + dx,
      y: st.panY + dy,
    });
  }, []);

  const onSvgPointerUp = useCallback(
    (e: React.PointerEvent) => {
      const st = pointerRef.current;
      if (!st.down || e.pointerId !== st.pointerId) return;
      st.down = false;
      try {
        (e.currentTarget as SVGSVGElement).releasePointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
      if (!st.panning) {
        placeOrRemoveColumn(e.clientX, e.clientY);
      }
      st.panning = false;
    },
    [placeOrRemoveColumn],
  );

  const dots = useMemo(
    () =>
      clicks.map((c, i) => (
        <circle
          key={c.id}
          cx={c.x_px}
          cy={c.y_px}
          r={12}
          fill="rgba(34,197,94,0.95)"
          stroke="#bbf7d0"
          strokeWidth={2.5}
          pointerEvents="none"
        >
          <title>{c.mark ?? `C${i + 1}`}</title>
        </circle>
      )),
    [clicks],
  );

  return (
    <div className={cn("flex h-full min-h-0 flex-1 flex-col gap-2 overflow-hidden p-3", className)}>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm text-slate-300">{he.planCropColumnClickHint}</p>
          <p className="text-xs text-slate-500">
            {clicks.length} {he.planCropColumns}
            {calibration.mm_per_px
              ? ` · ${calibration.mm_per_px.toFixed(2)} mm/px (${he.planCropFromPdfScale})`
              : ` · ${he.planCropPixelScaleOnly}`}
            {(calibration.x_grid_positions_mm?.length ?? 0) >= 2
              ? ` · X bays=${calibration.x_grid_positions_mm?.length} Y=${calibration.y_grid_positions_mm?.length ?? 0}`
              : null}
            {calibration.suggested_column_profile
              ? ` · ${calibration.suggested_column_profile}`
              : null}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            disabled={clicks.length === 0}
            aria-label={he.planCropUndoClick}
            onClick={onUndoLast}
          >
            <Undo2 className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className="h-8 w-8"
            aria-label={he.planCropZoomOut}
            onClick={() => {
              const vp = viewportRef.current;
              if (!vp) return;
              const r = vp.getBoundingClientRect();
              zoomAt(r.left + r.width / 2, r.top + r.height / 2, 1 / ZOOM_STEP);
            }}
          >
            <Minus className="h-4 w-4" />
          </Button>
          <span className="min-w-[3rem] text-center text-xs text-slate-400">
            {Math.round(scale * 100)}%
          </span>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className="h-8 w-8"
            aria-label={he.planCropZoomIn}
            onClick={() => {
              const vp = viewportRef.current;
              if (!vp) return;
              const r = vp.getBoundingClientRect();
              zoomAt(r.left + r.width / 2, r.top + r.height / 2, ZOOM_STEP);
            }}
          >
            <Plus className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            aria-label={he.planCropZoomReset}
            onClick={() => {
              setScale(1);
              setPan({ x: 0, y: 0 });
            }}
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <p className="shrink-0 text-[10px] text-slate-600">{he.planCropZoomPanHint}</p>
      <div
        ref={viewportRef}
        className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-slate-700 bg-slate-900"
      >
        <div
          className="absolute left-0 top-0 origin-top-left"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            width: "100%",
            height: "100%",
          }}
        >
          <div
            className="relative h-full w-full"
            style={{ aspectRatio: aspect, maxWidth: "100%", margin: "0 auto" }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={cropImageUrl}
              alt={he.planCropCanvasAlt}
              className="pointer-events-none absolute inset-0 h-full w-full select-none object-fill"
              draggable={false}
            />
            <svg
              ref={svgRef}
              xmlns="http://www.w3.org/2000/svg"
              viewBox={`0 0 ${cropW} ${cropH}`}
              preserveAspectRatio="none"
              className="absolute inset-0 z-10 h-full w-full cursor-crosshair touch-none"
              onPointerDown={onSvgPointerDown}
              onPointerMove={onSvgPointerMove}
              onPointerUp={onSvgPointerUp}
              onPointerCancel={onSvgPointerUp}
            >
              {/* Transparent hit layer — empty SVG does not receive clicks otherwise */}
              <rect
                x={0}
                y={0}
                width={cropW}
                height={cropH}
                fill="rgba(0,0,0,0.001)"
                pointerEvents="all"
              />
              <g pointerEvents="none">{dots}</g>
            </svg>
          </div>
        </div>
      </div>
      {calibration.notes.length > 0 ? (
        <ul className="shrink-0 list-inside list-disc text-xs text-amber-400/90">
          {calibration.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
