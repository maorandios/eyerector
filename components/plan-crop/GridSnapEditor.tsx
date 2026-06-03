"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Minus, Plus, RotateCcw } from "lucide-react";
import type { GridVertexDTO, RegionGridGeometryResult } from "@/lib/plan-crop/types";
import { gridVertexKey } from "@/lib/plan-crop/types";
import { he } from "@/lib/i18n/he";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const SNAP_RADIUS_PX = 22;
const MIN_SCALE = 0.2;
const MAX_SCALE = 8;
const ZOOM_STEP = 1.15;

type GridSnapEditorProps = {
  cropImageUrl: string;
  geometry: RegionGridGeometryResult;
  selectedKeys: ReadonlySet<string>;
  onToggleVertex: (vertex: GridVertexDTO) => void;
  className?: string;
};

function clientToSvg(svg: SVGSVGElement, clientX: number, clientY: number): { x: number; y: number } | null {
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const matrix = svg.getScreenCTM()?.inverse();
  if (!matrix) return null;
  const mapped = pt.matrixTransform(matrix);
  return { x: mapped.x, y: mapped.y };
}

function nearestVertex(
  vertices: GridVertexDTO[],
  x: number,
  y: number,
  radius: number,
): GridVertexDTO | null {
  const r2 = radius * radius;
  let best: GridVertexDTO | null = null;
  let bestD = r2;
  for (const v of vertices) {
    const d = (v.x_px - x) ** 2 + (v.y_px - y) ** 2;
    if (d <= bestD) {
      bestD = d;
      best = v;
    }
  }
  return best;
}

export function GridSnapEditor({
  cropImageUrl,
  geometry,
  selectedKeys,
  onToggleVertex,
  className,
}: GridSnapEditorProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panDrag = useRef<{ active: boolean; startX: number; startY: number; panX: number; panY: number }>({
    active: false,
    startX: 0,
    startY: 0,
    panX: 0,
    panY: 0,
  });

  useEffect(() => {
    const img = new Image();
    img.onload = () => setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
    img.src = cropImageUrl;
  }, [cropImageUrl]);

  const aspect = useMemo(() => {
    const w = geometry.crop_width_px;
    const h = geometry.crop_height_px;
    return `${w} / ${h}`;
  }, [geometry.crop_width_px, geometry.crop_height_px]);

  const clampScale = useCallback(
    (s: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s)),
    [],
  );

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
      const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      zoomAt(e.clientX, e.clientY, factor);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const handlePointer = useCallback(
    (clientX: number, clientY: number) => {
      if (panDrag.current.active) return;
      const svg = svgRef.current;
      if (!svg) return;
      const pt = clientToSvg(svg, clientX, clientY);
      if (!pt) return;
      const hit = nearestVertex(geometry.vertices, pt.x, pt.y, SNAP_RADIUS_PX);
      if (hit) onToggleVertex(hit);
    },
    [geometry.vertices, onToggleVertex],
  );

  const onPanPointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0 && e.button !== 1) return;
    const target = e.target as HTMLElement;
    if (target.closest("circle")) return;
    panDrag.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      panX: pan.x,
      panY: pan.y,
    };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, [pan.x, pan.y]);

  const onPanPointerMove = useCallback((e: React.PointerEvent) => {
    if (!panDrag.current.active) return;
    setPan({
      x: panDrag.current.panX + (e.clientX - panDrag.current.startX),
      y: panDrag.current.panY + (e.clientY - panDrag.current.startY),
    });
  }, []);

  const onPanPointerUp = useCallback((e: React.PointerEvent) => {
    panDrag.current.active = false;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  }, []);

  const resetView = useCallback(() => {
    setScale(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const dotR = (active: boolean) => (active ? 11 : 8) / scale;

  const vertexCircles = useMemo(
    () =>
      geometry.vertices.map((v) => {
        const key = gridVertexKey(v.grid_index_x, v.grid_index_y);
        const active = selectedKeys.has(key);
        return (
          <circle
            key={key}
            cx={v.x_px}
            cy={v.y_px}
            r={dotR(active)}
            fill={active ? "rgba(34,197,94,0.95)" : "rgba(15,23,42,0.65)"}
            stroke={active ? "#bbf7d0" : "rgba(34,197,94,0.95)"}
            strokeWidth={2 / scale}
            vectorEffect="non-scaling-stroke"
            className="cursor-pointer"
            data-ix={v.grid_index_x}
            data-iy={v.grid_index_y}
          />
        );
      }),
    [geometry.vertices, selectedKeys, scale],
  );

  return (
    <div className={cn("flex h-full min-h-0 flex-1 flex-col gap-2 overflow-hidden p-3", className)}>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm text-slate-300">{he.planCropGridEditorHint}</p>
          <p className="text-xs text-slate-500">
            {he.planCropGridLineCounts}: X={geometry.x_lines_px.length} Y={geometry.y_lines_px.length} ·{" "}
            {geometry.vertices.length} {he.planCropGridVertices} · {selectedKeys.size}{" "}
            {he.planCropColumns}
          </p>
        </div>
        <div className="flex items-center gap-1">
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
            onClick={resetView}
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <p className="shrink-0 text-[10px] text-slate-600">{he.planCropZoomPanHint}</p>
      <div
        ref={viewportRef}
        className="relative min-h-0 flex-1 cursor-grab overflow-hidden rounded-lg border border-slate-700 bg-slate-900 active:cursor-grabbing"
        onPointerDown={onPanPointerDown}
        onPointerMove={onPanPointerMove}
        onPointerUp={onPanPointerUp}
        onPointerCancel={onPanPointerUp}
      >
        <div
          className="absolute left-0 top-0 origin-top-left"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            width: "100%",
            maxWidth: "100%",
          }}
        >
          <div
            className="relative mx-auto w-full"
            style={{ aspectRatio: aspect, maxWidth: "min(100%, 1200px)" }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={cropImageUrl}
              alt={he.planCropCanvasAlt}
              className="absolute inset-0 h-full w-full object-fill select-none"
              draggable={false}
            />
            <svg
              ref={svgRef}
              xmlns="http://www.w3.org/2000/svg"
              viewBox={`0 0 ${geometry.crop_width_px} ${geometry.crop_height_px}`}
              preserveAspectRatio="none"
              className="absolute inset-0 h-full w-full touch-none"
              onClick={(e) => handlePointer(e.clientX, e.clientY)}
              onTouchEnd={(e) => {
                const t = e.changedTouches[0];
                if (t) handlePointer(t.clientX, t.clientY);
              }}
            >
              <g strokeWidth={1.5 / scale} vectorEffect="non-scaling-stroke" fill="none" pointerEvents="none">
                {geometry.x_lines_px.map((x, i) => (
                  <line
                    key={`x-${i}-${x.toFixed(2)}`}
                    x1={x}
                    y1={0}
                    x2={x}
                    y2={geometry.crop_height_px}
                    stroke="rgba(251,146,60,0.9)"
                  />
                ))}
                {geometry.y_lines_px.map((y, i) => (
                  <line
                    key={`y-${i}-${y.toFixed(2)}`}
                    x1={0}
                    y1={y}
                    x2={geometry.crop_width_px}
                    y2={y}
                    stroke="rgba(56,189,248,0.9)"
                  />
                ))}
              </g>
              <g pointerEvents="all">{vertexCircles}</g>
            </svg>
          </div>
        </div>
      </div>
      <div className="shrink-0 space-y-1">
        {naturalSize ? (
          <p className="text-[10px] text-slate-600">
            crop {naturalSize.w}×{naturalSize.h}px · server {geometry.crop_width_px}×
            {geometry.crop_height_px}px
          </p>
        ) : null}
        {geometry.notes.length > 0 ? (
          <ul className="list-inside list-disc text-xs text-amber-400/90">
            {geometry.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
