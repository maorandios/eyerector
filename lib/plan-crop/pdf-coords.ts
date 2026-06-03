import type { CropBoundsPt } from "@/lib/plan-crop/types";

export function normToPdfPoint(
  xNorm: number,
  yNorm: number,
  bounds: CropBoundsPt,
): { x_pt: number; y_pt: number } {
  const w = bounds.x1 - bounds.x0;
  const h = bounds.y1 - bounds.y0;
  return {
    x_pt: bounds.x0 + Math.max(0, Math.min(1, xNorm)) * w,
    y_pt: bounds.y0 + Math.max(0, Math.min(1, yNorm)) * h,
  };
}

export function pdfPointToNorm(
  x_pt: number,
  y_pt: number,
  bounds: CropBoundsPt,
): { x_norm: number; y_norm: number } {
  const w = bounds.x1 - bounds.x0;
  const h = bounds.y1 - bounds.y0;
  if (w <= 0 || h <= 0) return { x_norm: 0, y_norm: 0 };
  return {
    x_norm: (x_pt - bounds.x0) / w,
    y_norm: (y_pt - bounds.y0) / h,
  };
}

export function pdfLineToCropPx(
  coord_pt: number,
  origin_pt: number,
  cropSpan_pt: number,
  cropSpan_px: number,
): number {
  if (cropSpan_pt <= 0) return 0;
  return ((coord_pt - origin_pt) / cropSpan_pt) * cropSpan_px;
}

export function cropPxToNorm(x_px: number, y_px: number, cropW: number, cropH: number) {
  return {
    x_norm: cropW > 0 ? x_px / cropW : 0,
    y_norm: cropH > 0 ? y_px / cropH : 0,
  };
}
