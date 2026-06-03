"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Minus, Plus, RotateCcw } from "lucide-react";
import type { ColumnClick, RegionCropCalibrationResult } from "@/lib/plan-crop/types";
import type { SnappedColumn } from "@/lib/plan-crop/grid-snap";
import { makeColumnClickFromCanvas, stationsMmToLinesPx } from "@/lib/plan-crop/grid-snap";
import { he } from "@/lib/i18n/he";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const HIT_RADIUS_PX = 22;
const PAN_THRESHOLD_PX = 6;
const MIN_SCALE = 0.2;
const MAX_SCALE = 8;
const ZOOM_STEP = 1.15;

type GridMarkupCanvasProps = {
  cropImageUrl: string;
  calibration: RegionCropCalibrationResult;
  /** Raw clicks while marking */
  clicks?: ColumnClick[];
  /** Snapped positions for review (drawn on grid intersections) */
  snapped?: SnappedColumn[];
  mode: "mark" | "review";
  onAddClick?: (click: ColumnClick) => void;
  onRemoveClick?: (id: string) => void;
  className?: string;
};

function clientToSvgCoords(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
  cropW: number,
  cropH: number,
) {
  const rect = svg.getBoundingClientRect();
  return {
    x: ((clientX - rect.left) / Math.max(rect.width, 1)) * cropW,
    y: ((clientY - rect.top) / Math.max(rect.height, 1)) * cropH,
  };
}

function findClickNear(clicks: ColumnClick[], x: number, y: number, radius: number) {
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

export function GridMarkupCanvas({
  cropImageUrl,
  calibration,
  clicks = [],
  snapped = [],
  mode,
  onAddClick,
  onRemoveClick,
  className,
}: GridMarkupCanvasProps) {
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
  const { x_lines_px, y_lines_px } = useMemo(
    () => stationsMmToLinesPx(calibration, clicks),
    [calibration, clicks],
  );
  const hasGrid = x_lines_px.length >= 2 && y_lines_px.length >= 2;

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

  const handleMarkPointer = useCallback(
    (clientX: number, clientY: number) => {
      if (mode !== "mark" || !onAddClick || !onRemoveClick) return;
      const svg = svgRef.current;
      if (!svg) return;
      const pt = clientToSvgCoords(svg, clientX, clientY, cropW, cropH);
      const hit = findClickNear(clicks, pt.x, pt.y, HIT_RADIUS_PX);
      if (hit) {
        onRemoveClick(hit.id);
        return;
      }
      onAddClick(
        makeColumnClickFromCanvas(
          Math.max(0, Math.min(cropW, pt.x)),
          Math.max(0, Math.min(cropH, pt.y)),
          cropW,
          cropH,
          calibration.crop_bounds_pt ?? null,
        ),
      );
    },
    [clicks, cropH, cropW, mode, onAddClick, onRemoveClick],
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
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

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const st = pointerRef.current;
    if (!st.down || e.pointerId !== st.pointerId) return;
    const dx = e.clientX - st.startX;
    const dy = e.clientY - st.startY;
    if (!st.panning && Math.hypot(dx, dy) < PAN_THRESHOLD_PX) return;
    st.panning = true;
    setPan({ x: st.panX + dx, y: st.panY + dy });
  }, []);

  const onPointerUp = useCallback(
    (e: React.PointerEvent) => {
      const st = pointerRef.current;
      if (!st.down || e.pointerId !== st.pointerId) return;
      st.down = false;
      try {
        (e.currentTarget as SVGSVGElement).releasePointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
      if (!st.panning && mode === "mark") {
        handleMarkPointer(e.clientX, e.clientY);
      }
      /* review mode: pan only */
      st.panning = false;
    },
    [handleMarkPointer, mode],
  );

  const markDots = useMemo(
    () =>
      mode === "mark"
        ? clicks.map((c) => (
            <circle
              key={c.id}
              cx={c.x_px}
              cy={c.y_px}
              r={10}
              fill="rgba(34,197,94,0.9)"
              stroke="#bbf7d0"
              strokeWidth={2}
              pointerEvents="none"
            />
          ))
        : null,
    [clicks, mode],
  );

  const snappedDots = useMemo(
    () =>
      snapped.map((s) => (
        <g key={s.clickId} pointerEvents="none">
          <circle
            cx={s.x_px}
            cy={s.y_px}
            r={12}
            fill={s.duplicateCell ? "rgba(239,68,68,0.9)" : "rgba(34,197,94,0.95)"}
            stroke={s.duplicateCell ? "#fecaca" : "#bbf7d0"}
            strokeWidth={2.5}
          />
          <text
            x={s.x_px}
            y={s.y_px - 16}
            textAnchor="middle"
            fontSize={11}
            fill={s.duplicateCell ? "#fca5a5" : "#86efac"}
            fontWeight="600"
          >
            {s.mark}
          </text>
        </g>
      )),
    [snapped],
  );

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col gap-2", className)}>
      <div className="flex shrink-0 items-center justify-end gap-1">
        <Button
          type="button"
          size="icon"
          variant="secondary"
          className="h-8 w-8"
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
          onClick={() => {
            setScale(1);
            setPan({ x: 0, y: 0 });
          }}
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>
      {!hasGrid ? (
        <p className="text-xs text-amber-400">{he.planCropGridReviewNoPdfBays}</p>
      ) : null}
      <div
        ref={viewportRef}
        className={cn(
          "relative min-h-0 flex-1 overflow-hidden rounded-lg border border-slate-700 bg-slate-900",
          mode === "mark" ? "cursor-crosshair" : "cursor-default",
        )}
      >
        <div
          className="absolute left-0 top-0 origin-top-left"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            width: "100%",
            height: "100%",
          }}
        >
          <div className="relative mx-auto h-full w-full" style={{ aspectRatio: aspect }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={cropImageUrl}
              alt={he.planCropCanvasAlt}
              className="pointer-events-none absolute inset-0 h-full w-full select-none object-fill"
              draggable={false}
            />
            <svg
              ref={svgRef}
              viewBox={`0 0 ${cropW} ${cropH}`}
              preserveAspectRatio="none"
              className="absolute inset-0 z-10 h-full w-full touch-none"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
            >
              {mode === "mark" ? (
                <rect
                  x={0}
                  y={0}
                  width={cropW}
                  height={cropH}
                  fill="rgba(0,0,0,0.001)"
                  pointerEvents="all"
                />
              ) : (
                <rect
                  x={0}
                  y={0}
                  width={cropW}
                  height={cropH}
                  fill="transparent"
                  pointerEvents="all"
                />
              )}
              <g strokeWidth={1.5} fill="none" pointerEvents="none">
                {x_lines_px.map((x, i) => (
                  <line
                    key={`x-${i}-${x.toFixed(2)}`}
                    x1={x}
                    y1={0}
                    x2={x}
                    y2={cropH}
                    stroke="rgba(251,146,60,0.9)"
                  />
                ))}
                {y_lines_px.map((y, i) => (
                  <line
                    key={`y-${i}-${y.toFixed(2)}`}
                    x1={0}
                    y1={y}
                    x2={cropW}
                    y2={y}
                    stroke="rgba(56,189,248,0.9)"
                  />
                ))}
              </g>
              {markDots}
              {mode === "review" ? snappedDots : null}
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}
