"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { CropRectNorm } from "@/lib/plan-crop/types";
import { he } from "@/lib/i18n/he";

const CROP_STROKE = "#00ffcc";
const MIN_NORM = 0.05;

type Pt = { x: number; y: number };

type RegionCropCanvasProps = {
  imageUrl: string;
  cropRect: CropRectNorm | null;
  onCropChange: (rect: CropRectNorm | null) => void;
  onCropComplete?: (rect: CropRectNorm) => void;
};

function drawCropOverlay(
  canvas: HTMLCanvasElement,
  wrapW: number,
  wrapH: number,
  rect: CropRectNorm | null,
  draft: CropRectNorm | null,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx || wrapW <= 0 || wrapH <= 0) return;
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  const bw = Math.max(1, Math.round(wrapW * dpr));
  const bh = Math.max(1, Math.round(wrapH * dpr));
  if (canvas.width !== bw || canvas.height !== bh) {
    canvas.width = bw;
    canvas.height = bh;
  }
  canvas.style.width = `${wrapW}px`;
  canvas.style.height = `${wrapH}px`;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, bw, bh);
  ctx.scale(dpr, dpr);

  const r = draft ?? rect;
  if (!r || r.w < 0.001 || r.h < 0.001) return;

  const x = r.x * wrapW;
  const y = r.y * wrapH;
  const w = r.w * wrapW;
  const h = r.h * wrapH;

  ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
  ctx.fillRect(0, 0, wrapW, wrapH);
  ctx.clearRect(x, y, w, h);

  ctx.strokeStyle = CROP_STROKE;
  ctx.lineWidth = 2;
  ctx.strokeRect(x, y, w, h);
  ctx.fillStyle = "rgba(0, 255, 204, 0.12)";
  ctx.fillRect(x, y, w, h);
}

function normalizeRect(a: Pt, b: Pt): CropRectNorm {
  const x0 = Math.min(a.x, b.x);
  const y0 = Math.min(a.y, b.y);
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  return {
    x: x0,
    y: y0,
    w: Math.max(MIN_NORM, x1 - x0),
    h: Math.max(MIN_NORM, y1 - y0),
  };
}

export function RegionCropCanvas({
  imageUrl,
  cropRect,
  onCropChange,
  onCropComplete,
}: RegionCropCanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [draft, setDraft] = useState<CropRectNorm | null>(null);
  const anchorRef = useRef<Pt | null>(null);
  const draggingRef = useRef(false);

  const redraw = useCallback(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    drawCropOverlay(canvas, wrap.clientWidth, wrap.clientHeight, cropRect, draft);
  }, [cropRect, draft]);

  useEffect(() => {
    redraw();
  }, [redraw, imageUrl]);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => redraw());
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [redraw]);

  const toPt = useCallback((e: React.PointerEvent): Pt | null => {
    const el = wrapRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    };
  }, []);

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const p = toPt(e);
    if (!p) return;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* noop */
    }
    draggingRef.current = true;
    anchorRef.current = p;
    setDraft({ x: p.x, y: p.y, w: MIN_NORM, h: MIN_NORM });
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current || !anchorRef.current) return;
    const p = toPt(e);
    if (!p) return;
    const rect = normalizeRect(anchorRef.current, p);
    setDraft(rect);
  };

  const finishDrag = () => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    const rect = draft;
    anchorRef.current = null;
    setDraft(null);
    if (!rect || rect.w < MIN_NORM || rect.h < MIN_NORM) return;
    const clamped: CropRectNorm = {
      x: Math.min(1 - MIN_NORM, Math.max(0, rect.x)),
      y: Math.min(1 - MIN_NORM, Math.max(0, rect.y)),
      w: Math.min(1 - rect.x, rect.w),
      h: Math.min(1 - rect.y, rect.h),
    };
    onCropChange(clamped);
    onCropComplete?.(clamped);
  };

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-[#00ffcc]">{he.planCropDragHint}</p>
      <div
        ref={wrapRef}
        className={cn(
          "relative max-h-[55vh] w-full overflow-hidden rounded-lg border border-slate-700 bg-slate-900",
          "touch-none select-none",
        )}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl}
          alt={he.planCropCanvasAlt}
          className="block h-auto max-h-[55vh] w-full object-contain"
          draggable={false}
        />
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
        />
        <div
          className="absolute inset-0 touch-none"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={finishDrag}
          onPointerCancel={finishDrag}
        />
      </div>
    </div>
  );
}
