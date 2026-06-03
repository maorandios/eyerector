/** Canonical grid + columns (matches backend GridModelDTO). */

export type GridAxis = {
  lines_px: number[];
  stations_mm: number[];
  bays_mm: number[];
  labels: string[];
};

export type GridColumn = {
  id: string;
  mark: string;
  x_px: number;
  y_px: number;
  x_mm: number;
  y_mm: number;
  grid_ix: number;
  grid_iy: number;
  source: "detected" | "user";
  confidence: number;
};

export type GridModel = {
  crop_width_px: number;
  crop_height_px: number;
  mm_per_px_x: number;
  mm_per_px_y: number;
  span_width_mm: number;
  span_height_mm: number;
  axis_x: GridAxis;
  axis_y: GridAxis;
  columns: GridColumn[];
  suggested_column_profile?: string | null;
  notes: string[];
  provenance: Record<string, string>;
};

const MIN_GAP_PX = 8;

export function dedupeLines(lines: number[], minGap = MIN_GAP_PX): number[] {
  if (!lines.length) return [];
  const sorted = [...lines].sort((a, b) => a - b);
  const out = [sorted[0]];
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] - out[out.length - 1] >= minGap) out.push(sorted[i]);
  }
  return out;
}

export function baysFromStations(stations: number[]): number[] {
  if (stations.length < 2) return [];
  return stations.slice(1).map((s, i) => Math.round((s - stations[i]) * 10) / 10);
}

export function stationsFromBays(bays: number[]): number[] {
  const out = [0];
  for (const b of bays) out.push(Math.round((out[out.length - 1] + b) * 10) / 10);
  return out;
}

function nearestIndex(value: number, stations: number[]): number {
  return stations.reduce(
    (best, s, i) => (Math.abs(s - value) < Math.abs(stations[best] - value) ? i : best),
    0,
  );
}

export type GridLineRef = { axis: "x" | "y"; index: number };

const MIN_LINE_GAP_PX = 10;

/** mm stations derived from line px (authoritative for overlay edits). */
export function syncAxisFromLines(model: GridModel, axis: "x" | "y"): GridModel {
  const isX = axis === "x";
  const ax = isX ? model.axis_x : model.axis_y;
  const cropH = model.crop_height_px;
  const cropW = model.crop_width_px;
  const mm = isX ? model.mm_per_px_x : model.mm_per_px_y;
  const lines = dedupeLines([...ax.lines_px], MIN_LINE_GAP_PX);
  if (lines.length < 1) return model;
  const stations = isX
    ? lines.map((x) => Math.round(x * mm * 10) / 10)
    : lines.map((y) => Math.round((cropH - y) * mm * 10) / 10);
  const labels =
    lines.length === ax.labels.length
      ? ax.labels
      : isX
        ? lines.map((_, i) => String(i + 1))
        : lines.map((_, i) => String.fromCharCode(65 + i));
  const nextAxis: GridAxis = {
    lines_px: lines,
    stations_mm: stations,
    bays_mm: baysFromStations(stations),
    labels,
  };
  return {
    ...model,
    span_width_mm: isX ? (stations[stations.length - 1] ?? model.span_width_mm) : model.span_width_mm,
    span_height_mm: isX ? model.span_height_mm : (stations[stations.length - 1] ?? model.span_height_mm),
    axis_x: isX ? nextAxis : model.axis_x,
    axis_y: isX ? model.axis_y : nextAxis,
  };
}

export function findLineAt(
  x: number,
  y: number,
  model: GridModel,
  threshold = 14,
): GridLineRef | null {
  let best: GridLineRef | null = null;
  let bestD = threshold;
  model.axis_x.lines_px.forEach((lx, i) => {
    const d = Math.abs(x - lx);
    if (d < bestD) {
      bestD = d;
      best = { axis: "x", index: i };
    }
  });
  model.axis_y.lines_px.forEach((ly, i) => {
    const d = Math.abs(y - ly);
    if (d < bestD) {
      bestD = d;
      best = { axis: "y", index: i };
    }
  });
  return best;
}

export function moveGridLine(
  model: GridModel,
  axis: "x" | "y",
  index: number,
  newPx: number,
): GridModel {
  const isX = axis === "x";
  const cropSpan = isX ? model.crop_width_px : model.crop_height_px;
  const lines = [...(isX ? model.axis_x.lines_px : model.axis_y.lines_px)];
  if (index < 0 || index >= lines.length) return model;
  const oldPx = lines[index];
  const min = index > 0 ? lines[index - 1] + MIN_LINE_GAP_PX : 0;
  const max =
    index < lines.length - 1 ? lines[index + 1] - MIN_LINE_GAP_PX : cropSpan;
  lines[index] = Math.max(min, Math.min(max, newPx));
  let next: GridModel = isX
    ? { ...model, axis_x: { ...model.axis_x, lines_px: lines } }
    : { ...model, axis_y: { ...model.axis_y, lines_px: lines } };
  next = syncAxisFromLines(next, axis);
  next = {
    ...next,
    columns: next.columns.map((c) => {
      const stickX = isX && Math.abs(c.x_px - oldPx) < 32;
      const stickY = !isX && Math.abs(c.y_px - oldPx) < 32;
      const x = stickX ? lines[index] : c.x_px;
      const y = stickY ? next.axis_y.lines_px[index] ?? c.y_px : c.y_px;
      return columnAtPx(next, x, y, c);
    }),
  };
  return next;
}

export function addGridLine(
  model: GridModel,
  axis: "x" | "y",
  px: number,
): GridModel {
  const isX = axis === "x";
  const cropSpan = isX ? model.crop_width_px : model.crop_height_px;
  const lines = [...(isX ? model.axis_x.lines_px : model.axis_y.lines_px)];
  const pos = Math.max(0, Math.min(cropSpan, px));
  if (lines.some((v) => Math.abs(v - pos) < MIN_LINE_GAP_PX)) return model;
  lines.push(pos);
  lines.sort((a, b) => a - b);
  let next: GridModel = isX
    ? { ...model, axis_x: { ...model.axis_x, lines_px: lines } }
    : { ...model, axis_y: { ...model.axis_y, lines_px: lines } };
  next = syncAxisFromLines(next, axis);
  return {
    ...next,
    columns: next.columns.map((c) => columnAtPx(next, c.x_px, c.y_px, c)),
  };
}

export function removeGridLine(
  model: GridModel,
  axis: "x" | "y",
  index: number,
): GridModel {
  const isX = axis === "x";
  const lines = [...(isX ? model.axis_x.lines_px : model.axis_y.lines_px)];
  if (lines.length <= 2 || index < 0 || index >= lines.length) return model;
  lines.splice(index, 1);
  let next: GridModel = isX
    ? { ...model, axis_x: { ...model.axis_x, lines_px: lines } }
    : { ...model, axis_y: { ...model.axis_y, lines_px: lines } };
  next = syncAxisFromLines(next, axis);
  return {
    ...next,
    columns: next.columns.map((c) => columnAtPx(next, c.x_px, c.y_px, c)),
  };
}

/** Keep mm stations and px lines in sync after bay/station edits. */
export function syncAxisFromStations(
  model: GridModel,
  axis: "x" | "y",
): GridModel {
  const cropW = model.crop_width_px;
  const cropH = model.crop_height_px;
  const isX = axis === "x";
  const ax = isX ? model.axis_x : model.axis_y;
  const span = isX ? model.span_width_mm : model.span_height_mm;
  const spanPx = isX ? cropW : cropH;
  const stations = [...ax.stations_mm];
  if (stations.length < 2) return model;
  const lines_px = isX
    ? stations.map((s) => Math.round((s / span) * cropW * 100) / 100)
    : stations.map((s) => Math.round((cropH - (s / span) * cropH) * 100) / 100);
  const nextAxis: GridAxis = {
    lines_px: dedupeLines(lines_px),
    stations_mm: stations,
    bays_mm: baysFromStations(stations),
    labels: ax.labels,
  };
  return {
    ...model,
    span_width_mm: isX ? stations[stations.length - 1] : model.span_width_mm,
    span_height_mm: isX ? model.span_height_mm : stations[stations.length - 1],
    axis_x: isX ? nextAxis : model.axis_x,
    axis_y: isX ? model.axis_y : nextAxis,
  };
}

export function snapColumnToGrid(model: GridModel, col: GridColumn): GridColumn {
  const xLines = model.axis_x.lines_px;
  const yLines = model.axis_y.lines_px;
  const xs = model.axis_x.stations_mm;
  const ys = model.axis_y.stations_mm;
  if (xLines.length < 2 || yLines.length < 2) return col;
  const ix = nearestIndex(col.x_px, xLines);
  const iy = nearestIndex(col.y_px, yLines);
  return {
    ...col,
    grid_ix: ix,
    grid_iy: iy,
    x_px: xLines[Math.min(ix, xLines.length - 1)],
    y_px: yLines[Math.min(iy, yLines.length - 1)],
    x_mm: xs[Math.min(ix, xs.length - 1)] ?? col.x_mm,
    y_mm: ys[Math.min(iy, ys.length - 1)] ?? col.y_mm,
    source: col.source === "detected" ? "detected" : "user",
  };
}

export function snapAllColumns(model: GridModel): GridModel {
  return {
    ...model,
    columns: model.columns.map((c) => snapColumnToGrid(model, c)),
  };
}

function nextColumnMark(model: GridModel): string {
  let maxN = 0;
  for (const c of model.columns) {
    const m = /^C(\d+)/i.exec(c.mark.trim());
    if (m) maxN = Math.max(maxN, parseInt(m[1], 10));
  }
  return `C${maxN + 1}`;
}

/** New manual column: dot stays where you clicked (not pulled to grid intersection). */
export function addColumnAt(
  model: GridModel,
  x_px: number,
  y_px: number,
  mark?: string,
): GridModel {
  const cropW = model.crop_width_px;
  const cropH = model.crop_height_px;
  const x = Math.max(0, Math.min(cropW, x_px));
  const y = Math.max(0, Math.min(cropH, y_px));
  const xLines = model.axis_x.lines_px;
  const yLines = model.axis_y.lines_px;
  const xs = model.axis_x.stations_mm;
  const ys = model.axis_y.stations_mm;

  let ix = 0;
  let iy = 0;
  let x_mm = Math.round(x * model.mm_per_px_x * 10) / 10;
  let y_mm = Math.round((cropH - y) * model.mm_per_px_y * 10) / 10;

  if (xLines.length >= 2 && yLines.length >= 2) {
    ix = nearestIndex(x, xLines);
    iy = nearestIndex(y, yLines);
    x_mm = xs[Math.min(ix, xs.length - 1)] ?? x_mm;
    y_mm = ys[Math.min(iy, ys.length - 1)] ?? y_mm;
  }

  const col: GridColumn = {
    id: crypto.randomUUID(),
    mark: mark ?? nextColumnMark(model),
    x_px: x,
    y_px: y,
    x_mm,
    y_mm,
    grid_ix: ix,
    grid_iy: iy,
    source: "user",
    confidence: 1,
  };
  return { ...model, columns: [...model.columns, col] };
}

export function removeColumn(model: GridModel, id: string): GridModel {
  return { ...model, columns: model.columns.filter((c) => c.id !== id) };
}

function columnAtPx(
  model: GridModel,
  x_px: number,
  y_px: number,
  base: GridColumn,
): GridColumn {
  const cropW = model.crop_width_px;
  const cropH = model.crop_height_px;
  const x = Math.max(0, Math.min(cropW, x_px));
  const y = Math.max(0, Math.min(cropH, y_px));
  const xLines = model.axis_x.lines_px;
  const yLines = model.axis_y.lines_px;
  const xs = model.axis_x.stations_mm;
  const ys = model.axis_y.stations_mm;
  let ix = base.grid_ix;
  let iy = base.grid_iy;
  let x_mm = Math.round(x * model.mm_per_px_x * 10) / 10;
  let y_mm = Math.round((cropH - y) * model.mm_per_px_y * 10) / 10;
  if (xLines.length >= 2 && yLines.length >= 2) {
    ix = nearestIndex(x, xLines);
    iy = nearestIndex(y, yLines);
    x_mm = xs[Math.min(ix, xs.length - 1)] ?? x_mm;
    y_mm = ys[Math.min(iy, ys.length - 1)] ?? y_mm;
  }
  return {
    ...base,
    x_px: x,
    y_px: y,
    x_mm,
    y_mm,
    grid_ix: ix,
    grid_iy: iy,
    source: "user",
  };
}

export function updateColumnPosition(
  model: GridModel,
  id: string,
  x_px: number,
  y_px: number,
): GridModel {
  return {
    ...model,
    columns: model.columns.map((c) => {
      if (c.id !== id) return c;
      if (c.source === "user") {
        return columnAtPx(model, x_px, y_px, c);
      }
      return snapColumnToGrid(model, { ...c, x_px, y_px });
    }),
  };
}

/** Align model px coords when crop bitmap size differs from manifest px. */
export function scaleGridModelToImage(
  model: GridModel,
  imageWidth: number,
  imageHeight: number,
): GridModel {
  const w0 = Math.max(1, model.crop_width_px);
  const h0 = Math.max(1, model.crop_height_px);
  if (imageWidth === w0 && imageHeight === h0) return model;
  const sx = imageWidth / w0;
  const sy = imageHeight / h0;
  const scaleAxis = (ax: GridAxis, vertical: boolean): GridAxis => ({
    ...ax,
    lines_px: ax.lines_px.map((v) =>
      Math.round((vertical ? v * sx : v * sy) * 100) / 100,
    ),
  });
  return {
    ...model,
    crop_width_px: imageWidth,
    crop_height_px: imageHeight,
    mm_per_px_x: model.span_width_mm / imageWidth,
    mm_per_px_y: model.span_height_mm / imageHeight,
    axis_x: scaleAxis(model.axis_x, true),
    axis_y: scaleAxis(model.axis_y, false),
    columns: model.columns.map((c) => ({
      ...c,
      x_px: Math.round(c.x_px * sx * 100) / 100,
      y_px: Math.round(c.y_px * sy * 100) / 100,
    })),
  };
}

export function updateBay(
  model: GridModel,
  axis: "x" | "y",
  bayIndex: number,
  mm: number,
): GridModel {
  const ax = axis === "x" ? model.axis_x : model.axis_y;
  const bays = [...ax.bays_mm];
  if (bayIndex < 0 || bayIndex >= bays.length) return model;
  bays[bayIndex] = Math.max(40, mm);
  const stations = stationsFromBays(bays);
  const patched = {
    ...model,
    axis_x:
      axis === "x"
        ? { ...ax, stations_mm: stations, bays_mm: bays }
        : model.axis_x,
    axis_y:
      axis === "y"
        ? { ...ax, stations_mm: stations, bays_mm: bays }
        : model.axis_y,
  };
  return syncAxisFromStations(patched, axis);
}
