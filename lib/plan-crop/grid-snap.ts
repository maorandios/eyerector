import type {
  AlignedPin,
  ColumnClick,
  CropBoundsPt,
  RegionCropCalibrationResult,
} from "@/lib/plan-crop/types";

const SAME_COLUMN_PX = 14;
const CLUSTER_TOL_FRAC = 0.022;
const LINE_DEDUPE_PX = 2;

/** Remove duplicate coordinates (fixes React key collisions). */
export function dedupeLineCoords(lines: number[], minGap = LINE_DEDUPE_PX): number[] {
  if (!lines.length) return [];
  const sorted = [...lines].sort((a, b) => a - b);
  const out: number[] = [sorted[0]];
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] - out[out.length - 1] >= minGap) out.push(sorted[i]);
  }
  return out;
}

export type SnappedColumn = {
  clickId: string;
  grid_index_x: number;
  grid_index_y: number;
  x_mm: number;
  y_mm: number;
  x_px: number;
  y_px: number;
  x_norm: number;
  y_norm: number;
  snapped_x_pt: number;
  snapped_y_pt: number;
  mark: string;
  duplicateCell: boolean;
};

function clusterAxisPx(values: number[], cropSpanPx: number): number[] {
  if (!values.length) return [];
  const tol = Math.max(14, cropSpanPx * CLUSTER_TOL_FRAC);
  const sorted = [...values].sort((a, b) => a - b);
  const clusters: number[][] = [];
  for (const v of sorted) {
    const last = clusters[clusters.length - 1];
    if (!clusters.length || v - last[last.length - 1] > tol) {
      clusters.push([v]);
    } else {
      clusters[clusters.length - 1].push(v);
    }
  }
  return clusters.map((c) => c.reduce((a, b) => a + b, 0) / c.length);
}

function nearestIndex(value: number, stations: number[]): number {
  if (!stations.length) return 0;
  return stations.reduce(
    (best, s, i) => (Math.abs(s - value) < Math.abs(stations[best] - value) ? i : best),
    0,
  );
}

export function pdfDimensionStationsValid(cal: RegionCropCalibrationResult): boolean {
  const xs = cal.x_grid_positions_mm ?? [];
  const ys = cal.y_grid_positions_mm ?? [];
  const spanX = cal.span_width_mm ?? xs[xs.length - 1];
  const spanY = cal.span_height_mm ?? ys[ys.length - 1];
  return (
    xs.length >= 2 &&
    ys.length >= 2 &&
    xs[xs.length - 1] > xs[0] &&
    ys[ys.length - 1] > ys[0] &&
    !!spanX &&
    spanX > 0 &&
    !!spanY &&
    spanY > 0
  );
}

export function pdfGridStationsValid(cal: RegionCropCalibrationResult): boolean {
  const xPx = cal.grid_lines_x_px ?? [];
  const yPx = cal.grid_lines_y_px ?? [];
  if (xPx.length >= 2 && yPx.length >= 2) return true;
  const mm = cal.mm_per_px ?? cal.mm_per_px_x;
  return !!(mm && mm > 0 && pdfDimensionStationsValid(cal));
}

function mmPerAxis(cal: RegionCropCalibrationResult): { mmX: number; mmY: number } {
  const xs = cal.x_grid_positions_mm ?? [];
  const ys = cal.y_grid_positions_mm ?? [];
  const spanX = cal.span_width_mm ?? xs[xs.length - 1] ?? 1;
  const spanY = cal.span_height_mm ?? ys[ys.length - 1] ?? 1;
  const mmX = cal.mm_per_px_x ?? cal.mm_per_px ?? (spanX > 0 ? spanX / cal.crop_width_px : 1);
  const mmY = cal.mm_per_px_y ?? cal.mm_per_px ?? (spanY > 0 ? spanY / cal.crop_height_px : mmX);
  return { mmX, mmY };
}

function gridSpans(cal: RegionCropCalibrationResult): { spanX: number; spanY: number } {
  const xs = cal.x_grid_positions_mm ?? [];
  const ys = cal.y_grid_positions_mm ?? [];
  const lastX = xs.length ? xs[xs.length - 1] : 0;
  const lastY = ys.length ? ys[ys.length - 1] : 0;
  return {
    spanX: Math.max(cal.span_width_mm ?? 0, lastX) || 1,
    spanY: Math.max(cal.span_height_mm ?? 0, lastY) || 1,
  };
}

function clampCropPx(
  x_px: number,
  y_px: number,
  cropW: number,
  cropH: number,
): { x_px: number; y_px: number; x_norm: number; y_norm: number } {
  const x = Math.max(0, Math.min(cropW, x_px));
  const y = Math.max(0, Math.min(cropH, y_px));
  return {
    x_px: x,
    y_px: y,
    x_norm: cropW > 0 ? x / cropW : 0,
    y_norm: cropH > 0 ? y / cropH : 0,
  };
}

/** Crop mm with origin bottom-left (+Y up), matching PDF dimension chains. */
export function clickToCropMm(
  click: ColumnClick,
  cal: RegionCropCalibrationResult,
): { x_mm: number; y_mm: number } {
  const { mmX, mmY } = mmPerAxis(cal);
  const { spanY } = gridSpans(cal);
  return {
    x_mm: click.x_px * mmX,
    y_mm: spanY - click.y_px * mmY,
  };
}

/** Canvas px (top-left) from crop mm (bottom-left origin). */
export function mmToCropPx(
  x_mm: number,
  y_mm: number,
  cal: RegionCropCalibrationResult,
): { x_px: number; y_px: number; x_norm: number; y_norm: number } {
  const { spanX, spanY } = gridSpans(cal);
  const cropW = cal.crop_width_px;
  const cropH = cal.crop_height_px;
  const x_px = spanX > 0 ? (x_mm / spanX) * cropW : 0;
  const y_px = spanY > 0 ? cropH - (y_mm / spanY) * cropH : 0;
  return clampCropPx(x_px, y_px, cropW, cropH);
}

/** mm stations aligned 1:1 with detected grid lines in px. */
export function stationsAlignedWithLines(cal: RegionCropCalibrationResult): {
  xs_mm: number[];
  ys_mm: number[];
  x_lines_px: number[];
  y_lines_px: number[];
} {
  const { x_lines_px, y_lines_px } = stationsMmToLinesPx(cal, []);
  if (pdfDimensionStationsValid(cal)) {
    const xs_mm = (cal.x_grid_positions_mm ?? []).map((x) => Math.round(x * 10) / 10);
    const ys_mm = (cal.y_grid_positions_mm ?? []).map((y) => Math.round(y * 10) / 10);
    return { xs_mm, ys_mm, x_lines_px, y_lines_px };
  }
  const { mmX, mmY } = mmPerAxis(cal);
  const cropH = cal.crop_height_px;
  const xs_mm = x_lines_px.map((x) => Math.round(x * mmX * 10) / 10);
  const ys_mm = y_lines_px.map((y) => Math.round((cropH - y) * mmY * 10) / 10);
  return { xs_mm, ys_mm, x_lines_px, y_lines_px };
}

/** PDF grid lines for overlay (dimension fallback when server lines missing). */
export function pdfStationsToLinesPx(cal: RegionCropCalibrationResult): {
  x_lines_px: number[];
  y_lines_px: number[];
} {
  const xPx = dedupeLineCoords(cal.grid_lines_x_px ?? []);
  const yPx = dedupeLineCoords(cal.grid_lines_y_px ?? []);
  if (xPx.length >= 2 && yPx.length >= 2) {
    return { x_lines_px: xPx, y_lines_px: yPx };
  }
  if (!pdfGridStationsValid(cal)) return { x_lines_px: [], y_lines_px: [] };
  const xs = cal.x_grid_positions_mm ?? [];
  const ys = cal.y_grid_positions_mm ?? [];
  const { spanX, spanY } = gridSpans(cal);
  const cropW = cal.crop_width_px;
  const cropH = cal.crop_height_px;
  return {
    x_lines_px: dedupeLineCoords(xs.map((x) => (x / spanX) * cropW)),
    y_lines_px: dedupeLineCoords(ys.map((y) => cropH - (y / spanY) * cropH)),
  };
}

export function gridLinesFromClickClusters(
  clicks: ColumnClick[],
  cropW: number,
  cropH: number,
): { x_lines_px: number[]; y_lines_px: number[] } {
  if (clicks.length < 1) return { x_lines_px: [], y_lines_px: [] };
  return {
    x_lines_px: clusterAxisPx(
      clicks.map((c) => c.x_px),
      cropW,
    ),
    y_lines_px: clusterAxisPx(
      clicks.map((c) => c.y_px),
      cropH,
    ),
  };
}

/** Grid overlay lines: always prefer server vector px, never dimension pseudo-px. */
export function stationsMmToLinesPx(
  cal: RegionCropCalibrationResult,
  clicks: ColumnClick[] = [],
): { x_lines_px: number[]; y_lines_px: number[] } {
  const serverX = dedupeLineCoords(cal.grid_lines_x_px ?? []);
  const serverY = dedupeLineCoords(cal.grid_lines_y_px ?? []);
  if (serverX.length >= 2 && serverY.length >= 2) {
    return { x_lines_px: serverX, y_lines_px: serverY };
  }
  return gridLinesFromClickClusters(clicks, cal.crop_width_px, cal.crop_height_px);
}

/** Snap each click to nearest PDF grid station; 3D uses plan bay mm. */
export function snapColumnClicks(
  cal: RegionCropCalibrationResult,
  clicks: ColumnClick[],
): SnappedColumn[] {
  const cropW = cal.crop_width_px;
  const cropH = cal.crop_height_px;
  const { mmX, mmY } = mmPerAxis(cal);
  const usePdfMm = pdfDimensionStationsValid(cal);
  const pdfXs = cal.x_grid_positions_mm ?? [];
  const pdfYs = cal.y_grid_positions_mm ?? [];

  const { x_lines_px, y_lines_px } = stationsMmToLinesPx(cal, clicks);
  let xs: number[];
  let ys: number[];
  let xLinesPx: number[];
  let yLinesPx: number[];

  if (usePdfMm) {
    xs = pdfXs.map((x) => Math.round(x * 10) / 10);
    ys = pdfYs.map((y) => Math.round(y * 10) / 10);
    xLinesPx = x_lines_px;
    yLinesPx = y_lines_px;
  } else {
    xLinesPx = dedupeLineCoords(x_lines_px, 12).slice(0, 18);
    yLinesPx = dedupeLineCoords(y_lines_px, 12).slice(0, 8);
    xs = xLinesPx.map((x) => Math.round(x * mmX * 10) / 10);
    ys = yLinesPx.map((y) => Math.round((cropH - y) * mmY * 10) / 10);
  }

  const canSnap =
    usePdfMm || (xLinesPx.length >= 2 && yLinesPx.length >= 2 && xs.length >= 2 && ys.length >= 2);

  const xSorted = dedupeLineCoords(xLinesPx);
  const ySorted = dedupeLineCoords(yLinesPx);

  const snapped: SnappedColumn[] = clicks.map((click, i) => {
    let x_mm: number;
    let y_mm: number;
    let ix: number;
    let iy: number;
    let px: { x_px: number; y_px: number; x_norm: number; y_norm: number };

    if (canSnap && xSorted.length >= 2 && ySorted.length >= 2) {
      ix = nearestIndex(click.x_px, xSorted);
      iy = nearestIndex(click.y_px, ySorted);
      ix = Math.min(ix, xs.length - 1);
      iy = Math.min(iy, ys.length - 1);
      x_mm = xs[ix] ?? 0;
      y_mm = ys[iy] ?? 0;
      px = clampCropPx(xSorted[ix], ySorted[iy], cropW, cropH);
    } else {
      x_mm = Math.round(click.x_px * mmX * 10) / 10;
      y_mm = Math.round((cropH - click.y_px) * mmY * 10) / 10;
      ix = 0;
      iy = 0;
      px = clampCropPx(click.x_px, click.y_px, cropW, cropH);
    }

    x_mm = Math.round(x_mm * 10) / 10;
    y_mm = Math.round(y_mm * 10) / 10;

    return {
      clickId: click.id,
      grid_index_x: ix,
      grid_index_y: iy,
      x_mm,
      y_mm,
      x_px: px.x_px,
      y_px: px.y_px,
      x_norm: px.x_norm,
      y_norm: px.y_norm,
      snapped_x_pt: x_mm,
      snapped_y_pt: y_mm,
      mark: click.mark?.trim() || `C${i + 1}`,
      duplicateCell: false,
    };
  });

  const cellKeys = new Map<string, number[]>();
  snapped.forEach((s, idx) => {
    const key = `${s.grid_index_x}:${s.grid_index_y}`;
    const list = cellKeys.get(key) ?? [];
    list.push(idx);
    cellKeys.set(key, list);
  });
  for (const indices of cellKeys.values()) {
    if (indices.length <= 1) continue;
    for (let a = 0; a < indices.length; a++) {
      for (let b = a + 1; b < indices.length; b++) {
        const i = indices[a];
        const j = indices[b];
        const d = Math.hypot(
          snapped[i].x_px - snapped[j].x_px,
          snapped[i].y_px - snapped[j].y_px,
        );
        if (d <= SAME_COLUMN_PX) {
          snapped[i].duplicateCell = true;
          snapped[j].duplicateCell = true;
        }
      }
    }
  }

  return snapped;
}

export function duplicateCellGroups(snapped: SnappedColumn[]): Map<string, SnappedColumn[]> {
  const groups = new Map<string, SnappedColumn[]>();
  const used = new Set<string>();
  for (let i = 0; i < snapped.length; i++) {
    if (used.has(snapped[i].clickId)) continue;
    const cluster = [snapped[i]];
    used.add(snapped[i].clickId);
    for (let j = i + 1; j < snapped.length; j++) {
      if (used.has(snapped[j].clickId)) continue;
      const sameGrid =
        snapped[i].grid_index_x === snapped[j].grid_index_x &&
        snapped[i].grid_index_y === snapped[j].grid_index_y;
      if (!sameGrid) continue;
      const d = Math.hypot(
        snapped[i].x_px - snapped[j].x_px,
        snapped[i].y_px - snapped[j].y_px,
      );
      if (d <= SAME_COLUMN_PX) {
        cluster.push(snapped[j]);
        used.add(snapped[j].clickId);
      }
    }
    if (cluster.length > 1) {
      groups.set(cluster.map((c) => c.mark).join(","), cluster);
    }
  }
  return groups;
}

export function alignedPinsFromSnapped(snapped: SnappedColumn[]): AlignedPin[] {
  return snapped.map((s) => ({
    id: s.clickId,
    x_norm: s.x_norm,
    y_norm: s.y_norm,
    x_pt: s.x_mm,
    y_pt: s.y_mm,
    snapped_x_pt: s.snapped_x_pt,
    snapped_y_pt: s.snapped_y_pt,
    grid_index_x: s.grid_index_x,
    grid_index_y: s.grid_index_y,
    mark: s.mark,
  }));
}

export function makeColumnClickFromCanvas(
  x_px: number,
  y_px: number,
  cropW: number,
  cropH: number,
  bounds?: CropBoundsPt | null,
): ColumnClick {
  const x_norm = cropW > 0 ? x_px / cropW : 0;
  const y_norm = cropH > 0 ? y_px / cropH : 0;
  let x_pt: number | null = null;
  let y_pt: number | null = null;
  if (bounds) {
    x_pt = bounds.x0 + x_norm * (bounds.x1 - bounds.x0);
    y_pt = bounds.y0 + y_norm * (bounds.y1 - bounds.y0);
  }
  return {
    id: crypto.randomUUID(),
    x_norm,
    y_norm,
    x_px,
    y_px,
    x_pt,
    y_pt,
  };
}

/** Finish API needs original crop px (0..crop); mm snap is applied server-side. */
export function clicksForFinish(
  clicks: ColumnClick[],
  snapped: SnappedColumn[],
  cal: RegionCropCalibrationResult,
): ColumnClick[] {
  const byId = new Map(snapped.map((s) => [s.clickId, s]));
  const cropW = Math.max(1, cal.crop_width_px);
  const cropH = Math.max(1, cal.crop_height_px);
  return clicks.map((click) => {
    const s = byId.get(click.id);
    const x_px = Math.max(0, Math.min(cropW, click.x_px));
    const y_px = Math.max(0, Math.min(cropH, click.y_px));
    return {
      ...click,
      mark: s?.mark ?? click.mark,
      x_px,
      y_px,
      x_norm: x_px / cropW,
      y_norm: y_px / cropH,
    };
  });
}
