"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Minus, Plus, RotateCcw, Trash2 } from "lucide-react";
import {
  addColumnAt,
  addGridLine,
  findLineAt,
  moveGridLine,
  removeColumn,
  removeGridLine,
  scaleGridModelToImage,
  snapAllColumns,
  updateColumnPosition,
  type GridColumn,
  type GridLineRef,
  type GridModel,
} from "@/lib/plan-crop/grid-model";
import { he } from "@/lib/i18n/he";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const HIT_RADIUS = 20;
const LINE_HIT = 14;
const PAN_THRESHOLD = 6;
const MIN_SCALE = 0.2;
const MAX_SCALE = 8;
const ZOOM_STEP = 1.15;

type GridModelEditorProps = {
  cropImageUrl: string;
  model: GridModel;
  onChange: (model: GridModel) => void;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  className?: string;
};

function clientToSvgPoint(svg: SVGSVGElement, clientX: number, clientY: number) {
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const matrix = svg.getScreenCTM();
  if (!matrix) return { x: 0, y: 0 };
  const local = pt.matrixTransform(matrix.inverse());
  return { x: local.x, y: local.y };
}

export function GridModelEditor({
  cropImageUrl,
  model,
  onChange,
  selectedId: selectedIdProp,
  onSelect,
  className,
}: GridModelEditorProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const dragId = useRef<string | null>(null);
  const dragLine = useRef<GridLineRef | null>(null);
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
  const [fitScale, setFitScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [viewSize, setViewSize] = useState({
    w: model.crop_width_px,
    h: model.crop_height_px,
  });
  const [selectedIdLocal, setSelectedIdLocal] = useState<string | null>(null);
  const [selectedLine, setSelectedLine] = useState<GridLineRef | null>(null);
  const selectedId = selectedIdProp ?? selectedIdLocal;
  const setSelectedId = (id: string | null) => {
    setSelectedIdLocal(id);
    onSelect?.(id);
  };

  const cropW = viewSize.w;
  const cropH = viewSize.h;

  useEffect(() => {
    setViewSize({ w: model.crop_width_px, h: model.crop_height_px });
  }, [model.crop_width_px, model.crop_height_px]);

  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp || cropW < 1 || cropH < 1) return;
    const fit = Math.min(vp.clientWidth / cropW, vp.clientHeight / cropH, 1);
    setFitScale(fit);
    const ro = new ResizeObserver(() => {
      const f = Math.min(vp.clientWidth / cropW, vp.clientHeight / cropH, 1);
      setFitScale(f);
    });
    ro.observe(vp);
    return () => ro.disconnect();
  }, [cropW, cropH]);

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
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const findColumn = useCallback(
    (x: number, y: number) => {
      const r2 = HIT_RADIUS * HIT_RADIUS;
      let best: GridColumn | null = null;
      let bestD = r2;
      for (const c of model.columns) {
        const d = (c.x_px - x) ** 2 + (c.y_px - y) ** 2;
        if (d <= bestD) {
          bestD = d;
          best = c;
        }
      }
      return best;
    },
    [model.columns],
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      const svg = svgRef.current;
      if (!svg) return;
      const { x, y } = clientToSvgPoint(svg, e.clientX, e.clientY);
      const lineHit = findLineAt(x, y, model, LINE_HIT);
      const col = lineHit ? null : findColumn(x, y);
      pointerRef.current = {
        down: true,
        panning: false,
        startX: e.clientX,
        startY: e.clientY,
        panX: pan.x,
        panY: pan.y,
        pointerId: e.pointerId,
      };
      dragLine.current = null;
      if (lineHit) {
        dragLine.current = lineHit;
        setSelectedLine(lineHit);
        setSelectedId(null);
        svg.setPointerCapture(e.pointerId);
      } else if (col) {
        dragId.current = col.id;
        setSelectedId(col.id);
        setSelectedLine(null);
        svg.setPointerCapture(e.pointerId);
      } else {
        dragId.current = null;
        setSelectedId(null);
        setSelectedLine(null);
      }
    },
    [findColumn, model, pan.x, pan.y],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const pr = pointerRef.current;
      if (!pr.down) return;
      const svg = svgRef.current;
      if (dragLine.current && svg) {
        const { x, y } = clientToSvgPoint(svg, e.clientX, e.clientY);
        const ref = dragLine.current;
        const pos = ref.axis === "x" ? x : y;
        onChange(moveGridLine(model, ref.axis, ref.index, pos));
        return;
      }
      if (dragId.current && svg) {
        const { x, y } = clientToSvgPoint(svg, e.clientX, e.clientY);
        onChange(updateColumnPosition(model, dragId.current, x, y));
        return;
      }
      const dx = e.clientX - pr.startX;
      const dy = e.clientY - pr.startY;
      if (!pr.panning && Math.hypot(dx, dy) > PAN_THRESHOLD) pr.panning = true;
      if (pr.panning) setPan({ x: pr.panX + dx, y: pr.panY + dy });
    },
    [model, onChange],
  );

  const onPointerUp = useCallback(
    (e: React.PointerEvent) => {
      const svg = svgRef.current;
      const pr = pointerRef.current;
      if (!pr.down) return;
      if (!dragId.current && !dragLine.current && !pr.panning && svg) {
        const { x, y } = clientToSvgPoint(svg, e.clientX, e.clientY);
        const clamped = {
          x: Math.max(0, Math.min(cropW, x)),
          y: Math.max(0, Math.min(cropH, y)),
        };
        onChange(addColumnAt(model, clamped.x, clamped.y));
      }
      dragId.current = null;
      dragLine.current = null;
      pr.down = false;
      pr.panning = false;
      try {
        svg?.releasePointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
    },
    [cropW, cropH, model, onChange],
  );

  const drawW = cropW * fitScale * scale;
  const drawH = cropH * fitScale * scale;

  const gridLines = useMemo(
    () => (
      <g fill="none">
        {model.axis_x.lines_px.map((x, i) => {
          const sel = selectedLine?.axis === "x" && selectedLine.index === i;
          return (
            <g key={`x-${i}-${x.toFixed(1)}`}>
              <line
                x1={x}
                y1={0}
                x2={x}
                y2={cropH}
                stroke="transparent"
                strokeWidth={18}
                pointerEvents="stroke"
                style={{ cursor: "ew-resize" }}
              />
              <line
                x1={x}
                y1={0}
                x2={x}
                y2={cropH}
                stroke={sel ? "rgba(250,204,21,0.98)" : "rgba(251,146,60,0.92)"}
                strokeWidth={sel ? 2.5 : 1.5}
                pointerEvents="none"
              />
            </g>
          );
        })}
        {model.axis_y.lines_px.map((y, i) => {
          const sel = selectedLine?.axis === "y" && selectedLine.index === i;
          return (
            <g key={`y-${i}-${y.toFixed(1)}`}>
              <line
                x1={0}
                y1={y}
                x2={cropW}
                y2={y}
                stroke="transparent"
                strokeWidth={18}
                pointerEvents="stroke"
                style={{ cursor: "ns-resize" }}
              />
              <line
                x1={0}
                y1={y}
                x2={cropW}
                y2={y}
                stroke={sel ? "rgba(250,204,21,0.98)" : "rgba(56,189,248,0.92)"}
                strokeWidth={sel ? 2.5 : 1.5}
                pointerEvents="none"
              />
            </g>
          );
        })}
      </g>
    ),
    [model, cropW, cropH, selectedLine],
  );

  const columnDots = useMemo(
    () =>
      model.columns.map((c) => (
        <g key={c.id} pointerEvents="none">
          <circle
            cx={c.x_px}
            cy={c.y_px}
            r={selectedId === c.id ? 14 : 11}
            fill={
              selectedId === c.id ? "rgba(59,130,246,0.95)" : "rgba(34,197,94,0.92)"
            }
            stroke={selectedId === c.id ? "#93c5fd" : "#bbf7d0"}
            strokeWidth={2.5}
          />
          <text
            x={c.x_px}
            y={c.y_px - 16}
            textAnchor="middle"
            fontSize={11}
            fill="#86efac"
            fontWeight="600"
          >
            {c.mark}
          </text>
        </g>
      )),
    [model.columns, selectedId],
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
      <p className="text-[11px] text-slate-500">{he.planCropGridModelHint}</p>
      <div className="flex flex-wrap gap-1">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 text-[10px]"
          onClick={() =>
            onChange(addGridLine(model, "x", model.crop_width_px / 2))
          }
        >
          {he.planCropGridModelAddLineX}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 text-[10px]"
          onClick={() =>
            onChange(addGridLine(model, "y", model.crop_height_px / 2))
          }
        >
          {he.planCropGridModelAddLineY}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 text-[10px]"
          disabled={!selectedLine}
          onClick={() => {
            if (!selectedLine) return;
            onChange(removeGridLine(model, selectedLine.axis, selectedLine.index));
            setSelectedLine(null);
          }}
        >
          {he.planCropGridModelDeleteLine}
        </Button>
      </div>
      {selectedLine ? (
        <p className="text-[10px] text-amber-400/90">
          {he.planCropGridModelLineSelected}:{" "}
          {selectedLine.axis === "x"
            ? (model.axis_x.labels[selectedLine.index] ?? String(selectedLine.index + 1))
            : (model.axis_y.labels[selectedLine.index] ??
              String.fromCharCode(65 + selectedLine.index))}
        </p>
      ) : null}
      <div
        ref={viewportRef}
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-lg border border-slate-700 bg-slate-900"
      >
        <div
          className="relative shrink-0 origin-center"
          style={{
            width: drawW,
            height: drawH,
            transform: `translate(${pan.x}px, ${pan.y}px)`,
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={cropImageUrl}
            alt={he.planCropCanvasAlt}
            width={drawW}
            height={drawH}
            className="block select-none"
            draggable={false}
            onLoad={(e) => {
              const img = e.currentTarget;
              const iw = img.naturalWidth;
              const ih = img.naturalHeight;
              if (iw < 1 || ih < 1) return;
              setViewSize({ w: iw, h: ih });
              if (
                Math.abs(iw - model.crop_width_px) > 2 ||
                Math.abs(ih - model.crop_height_px) > 2
              ) {
                onChange(scaleGridModelToImage(model, iw, ih));
              }
            }}
          />
          <svg
            ref={svgRef}
            viewBox={`0 0 ${cropW} ${cropH}`}
            preserveAspectRatio="none"
            className="absolute inset-0 z-10 h-full w-full cursor-crosshair touch-none select-none"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            <rect
              x={0}
              y={0}
              width={cropW}
              height={cropH}
              fill="transparent"
              pointerEvents="none"
            />
            {gridLines}
            {columnDots}
          </svg>
        </div>
      </div>
    </div>
  );
}

type GridModelPanelProps = {
  model: GridModel;
  onChange: (model: GridModel) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  isLoading: boolean;
  onBack: () => void;
  onApprove: () => void;
};

export function GridModelPanel({
  model,
  onChange,
  selectedId,
  onSelect,
  isLoading,
  onBack,
  onApprove,
}: GridModelPanelProps) {
  const selected = model.columns.find((c) => c.id === selectedId);

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">{he.planCropGridModelTitle}</h2>
        <p className="text-xs text-slate-400">{he.planCropGridModelSubtitle}</p>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-400">
        <dt>{he.planCropGridReviewRefLines} X</dt>
        <dd className="text-slate-200">{model.axis_x.lines_px.length}</dd>
        <dt>{he.planCropGridReviewRefLines} Y</dt>
        <dd className="text-slate-200">{model.axis_y.lines_px.length}</dd>
        <dt>{he.planCropColumns}</dt>
        <dd className="text-slate-200">{model.columns.length}</dd>
        <dt>mm/px X</dt>
        <dd className="text-slate-200">{model.mm_per_px_x.toFixed(2)}</dd>
      </dl>
      {model.notes.length > 0 ? (
        <ul className="max-h-20 list-inside list-disc overflow-y-auto text-[11px] text-slate-500">
          {model.notes.slice(0, 6).map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      ) : null}
      {selected ? (
        <div className="flex items-center gap-2 rounded border border-slate-700 p-2 text-xs">
          <span className="text-slate-300">{selected.mark}</span>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              onChange(removeColumn(model, selected.id));
              onSelect(null);
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ) : null}
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => onChange(snapAllColumns(model))}
      >
        {he.planCropGridModelResnap}
      </Button>
      <div className="max-h-36 overflow-y-auto rounded border border-slate-700">
        <table className="w-full text-left text-[11px]">
          <thead className="sticky top-0 bg-slate-900 text-slate-500">
            <tr>
              <th className="px-2 py-1">{he.planCropGridReviewMark}</th>
              <th className="px-2 py-1">X</th>
              <th className="px-2 py-1">Y</th>
              <th className="px-2 py-1">mm</th>
            </tr>
          </thead>
          <tbody>
            {model.columns.map((c) => (
              <tr
                key={c.id}
                className={cn(
                  "cursor-pointer",
                  c.id === selectedId ? "bg-slate-800 text-slate-100" : "text-slate-400",
                )}
                onClick={() => onSelect(c.id)}
              >
                <td className="px-2 py-0.5">{c.mark}</td>
                <td className="px-2 py-0.5">{c.grid_ix + 1}</td>
                <td className="px-2 py-0.5">
                  {model.axis_y.labels[c.grid_iy] ?? String.fromCharCode(65 + c.grid_iy)}
                </td>
                <td className="px-2 py-0.5">
                  {Math.round(c.x_mm)},{Math.round(c.y_mm)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button type="button" variant="ghost" disabled={isLoading} onClick={onBack}>
        {he.planCropBackToCrop}
      </Button>
      <Button
        type="button"
        disabled={isLoading || model.columns.length === 0}
        onClick={onApprove}
        className="bg-[#00ffcc] text-slate-950 hover:bg-[#00e6b8]"
      >
        {he.planCropGridModelApprove}
      </Button>
    </div>
  );
}
