import { resolveGridStations } from "@/lib/plan-crop/grid-normalize";

export type CropRectNorm = {
  x: number;
  y: number;
  w: number;
  h: number;
};

export type PageAsset = {
  page_index: number;
  width_px: number;
  height_px: number;
  url: string;
};

export type UploadPdfResult = {
  project_id: string;
  filename: string;
  page_count: number;
  base_url: string;
  pages: PageAsset[];
};

export type JsonValue = string | number | boolean | string[];

export type DetectedParameterEntry = {
  key: string;
  value: string;
};

export type LayoutMode = "dense_matrix" | "sparse_intersections";

export type ColumnPlacement = {
  id: string;
  x_mm: number;
  y_mm: number;
  profile_name: string;
  height_mm: number;
  mark?: string | null;
};

export type ActiveColumnIntersection = {
  grid_index_x: number;
  grid_index_y: number;
  mark?: string | null;
  profile_name?: string | null;
};

export type ColumnMarkProfile = {
  mark: string;
  profile_name: string;
};

export type RegionStructuralAnalysis = {
  element_type: "grid" | "truss" | "mezzanine" | "staircase" | "unknown";
  confidence: number;
  detected_parameters: DetectedParameterEntry[];
  x_grid_positions_mm?: number[];
  y_grid_positions_mm?: number[];
  x_bay_spacings_mm?: number[];
  y_bay_spacings_mm?: number[];
  column_placements?: ColumnPlacement[];
  layout_mode?: LayoutMode;
  active_column_intersections?: ActiveColumnIntersection[];
  column_profile_by_mark?: ColumnMarkProfile[];
  notes?: string | null;
};

export function usesSparsePlacement(analysis: RegionStructuralAnalysis): boolean {
  return (
    analysis.layout_mode === "sparse_intersections" ||
    (analysis.active_column_intersections?.length ?? 0) >= 1
  );
}

/** Estimate column count for UI preview (sparse list, explicit placements, or dense grid). */
export function estimateColumnCount(analysis: RegionStructuralAnalysis): number {
  if (usesSparsePlacement(analysis)) {
    return analysis.active_column_intersections?.length ?? 0;
  }
  if (analysis.column_placements?.length) {
    return analysis.column_placements.length;
  }
  const edited = parametersToRecord(analysis.detected_parameters);
  const { xs, ys } = gridStationsFromEdited(edited, analysis);
  if (xs.length >= 2 && ys.length >= 2) return xs.length * ys.length;
  return 0;
}

export function parseOrderedMmList(value: JsonValue | undefined): number[] {
  if (value === undefined || value === null) return [];
  if (Array.isArray(value)) {
    return value
      .flatMap((v) => parseOrderedMmList(v))
      .filter((n) => Number.isFinite(n));
  }
  const text = String(value).trim();
  if (!text) return [];
  return text
    .split(/[,;\s]+/)
    .map((s) => parseFloat(s.replace(/,/g, "")))
    .filter((n) => Number.isFinite(n));
}

export function parseMmList(value: JsonValue | undefined): number[] {
  const ordered = parseOrderedMmList(value);
  return [...ordered].sort((a, b) => a - b);
}

const MARK_KEY_RE = /^(?:column_)?(C\d+)(?:_profile)?$/i;

export function profilesFromEdited(
  edited: Record<string, JsonValue>,
  existing: ColumnMarkProfile[] = [],
): ColumnMarkProfile[] {
  const map = new Map(existing.map((e) => [e.mark.toUpperCase(), e.profile_name]));
  for (const [key, val] of Object.entries(edited)) {
    const m = key.match(MARK_KEY_RE);
    if (!m || val === undefined || val === null) continue;
    const profile = String(val).trim().split(/\s+/)[0];
    if (profile && !/^-?\d+(\.\d+)?$/.test(profile)) {
      map.set(m[1].toUpperCase(), profile);
    }
  }
  return [...map.entries()].map(([mark, profile_name]) => ({ mark, profile_name }));
}

function formatMmList(values: number[]): string {
  return values
    .map((v) => (Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10)))
    .join(", ");
}

function upsertDetectedParameter(
  entries: DetectedParameterEntry[],
  key: string,
  value: string,
): DetectedParameterEntry[] {
  const next = entries.filter((e) => e.key !== key);
  next.push({ key, value });
  return next;
}

function collectAxisLists(
  editedParameters: Record<string, JsonValue>,
  analysis: RegionStructuralAnalysis | undefined,
  axis: "x" | "y",
): { ordered: number[][]; bays: number[][] } {
  const ordered: number[][] = [];
  const bays: number[][] = [];
  const gridKey = axis === "x" ? "grid_lines_x_mm" : "grid_lines_y_mm";
  const posKey = axis === "x" ? "x_grid_positions_mm" : "y_grid_positions_mm";
  const bayKey = axis === "x" ? "x_bay_spacings_mm" : "y_bay_spacings_mm";

  const fromEditedGrid = parseOrderedMmList(editedParameters[gridKey]);
  const fromEditedPos = parseOrderedMmList(editedParameters[posKey]);
  const fromEditedBays = parseOrderedMmList(editedParameters[bayKey]);
  if (fromEditedGrid.length) ordered.push(fromEditedGrid);
  if (fromEditedPos.length) ordered.push(fromEditedPos);
  if (fromEditedBays.length) bays.push(fromEditedBays);

  const arr = axis === "x" ? analysis?.x_grid_positions_mm : analysis?.y_grid_positions_mm;
  const bayArr = axis === "x" ? analysis?.x_bay_spacings_mm : analysis?.y_bay_spacings_mm;
  if (arr?.length) ordered.push(arr);
  if (bayArr?.length) bays.push(bayArr);

  return { ordered, bays };
}

/** Parse grid fields into cumulative mm stations (same rules as Python compiler). */
export function gridStationsFromEdited(
  editedParameters: Record<string, JsonValue>,
  analysis?: RegionStructuralAnalysis,
): { xs: number[]; ys: number[] } {
  const xLists = collectAxisLists(editedParameters, analysis, "x");
  const yLists = collectAxisLists(editedParameters, analysis, "y");
  const xs = resolveGridStations(xLists.ordered, xLists.bays);
  const ys = resolveGridStations(yLists.ordered, yLists.bays);
  return { xs, ys };
}

/** Overrides sent alongside analysis — grid_lines_* strings win over sparse arrays. */
export function parameterOverridesForCompile(
  editedParameters: Record<string, JsonValue>,
  analysis?: RegionStructuralAnalysis,
): Record<string, JsonValue> {
  const { xs, ys } = gridStationsFromEdited(editedParameters, analysis);
  const out: Record<string, JsonValue> = { ...editedParameters };
  if (xs.length >= 2) {
    out.grid_lines_x_mm = formatMmList(xs);
    out.x_grid_positions_mm = formatMmList(xs);
  }
  if (ys.length >= 2) {
    out.grid_lines_y_mm = formatMmList(ys);
    out.y_grid_positions_mm = formatMmList(ys);
  }
  return out;
}

function gridExtractionSource(analysis: RegionStructuralAnalysis): string {
  return (
    analysis.detected_parameters?.find((e) => e.key === "grid_extraction_source")?.value ?? ""
  );
}

/** Plan-crop column clicks must keep exact mm placements (never sparse grid remap). */
export function isColumnClickLayout(analysis: RegionStructuralAnalysis): boolean {
  const src = gridExtractionSource(analysis);
  return src.includes("column_clicks");
}

/**
 * Build analysis payload for compile/preview: sync grid_lines into arrays.
 * Column-click layouts always keep dense_matrix + column_placements at click mm.
 */
export function analysisForCompile(
  analysis: RegionStructuralAnalysis,
  editedParameters: Record<string, JsonValue>,
): RegionStructuralAnalysis {
  const { xs, ys } = gridStationsFromEdited(editedParameters, analysis);
  const clickLayout = isColumnClickLayout(analysis);
  const hasPlacements = (analysis.column_placements?.length ?? 0) > 0;

  if (clickLayout && hasPlacements) {
    const column_profile_by_mark = profilesFromEdited(
      editedParameters,
      analysis.column_profile_by_mark ?? [],
    );
    return {
      ...analysis,
      layout_mode: "dense_matrix",
      column_placements: analysis.column_placements,
      active_column_intersections: [],
      column_profile_by_mark,
      x_grid_positions_mm: xs.length >= 2 ? xs : analysis.x_grid_positions_mm,
      y_grid_positions_mm: ys.length >= 2 ? ys : analysis.y_grid_positions_mm,
    };
  }

  const sparse = usesSparsePlacement(analysis);
  const hasExplicit =
    hasPlacements || (analysis.active_column_intersections?.length ?? 0) > 0;
  const gridCells = xs.length >= 2 && ys.length >= 2 ? xs.length * ys.length : 0;
  const autoSparse =
    hasExplicit &&
    gridCells > 0 &&
    (analysis.column_placements?.length ?? 0) < gridCells;
  const layoutMode: LayoutMode =
    sparse || autoSparse
      ? "sparse_intersections"
      : (analysis.layout_mode ?? "dense_matrix");
  const useDenseMatrix =
    xs.length >= 2 && ys.length >= 2 && layoutMode === "dense_matrix" && !hasExplicit;

  let detected_parameters = [...(analysis.detected_parameters ?? [])];
  if (xs.length >= 2) {
    detected_parameters = upsertDetectedParameter(
      detected_parameters,
      "grid_lines_x_mm",
      formatMmList(xs),
    );
  }
  if (ys.length >= 2) {
    detected_parameters = upsertDetectedParameter(
      detected_parameters,
      "grid_lines_y_mm",
      formatMmList(ys),
    );
  }

  const column_profile_by_mark = profilesFromEdited(
    editedParameters,
    analysis.column_profile_by_mark ?? [],
  );

  return {
    ...analysis,
    detected_parameters,
    x_grid_positions_mm: xs.length >= 2 ? xs : analysis.x_grid_positions_mm,
    y_grid_positions_mm: ys.length >= 2 ? ys : analysis.y_grid_positions_mm,
    active_column_intersections: analysis.active_column_intersections,
    column_profile_by_mark,
    layout_mode: layoutMode,
    column_placements: useDenseMatrix ? [] : analysis.column_placements,
  };
}

export function parametersToRecord(
  entries: DetectedParameterEntry[] | Record<string, JsonValue> | undefined,
): Record<string, JsonValue> {
  if (!entries) return {};
  if (!Array.isArray(entries)) return { ...entries };
  const out: Record<string, JsonValue> = {};
  for (const { key, value } of entries) {
    const raw = value.trim();
    const n = Number(raw.replace(/,/g, ""));
    if (raw !== "" && !Number.isNaN(n) && /^-?\d/.test(raw)) {
      out[key] = n;
    } else {
      out[key] = raw;
    }
  }
  return out;
}

export type PdfGridMeta = {
  attempted: boolean;
  applied: boolean;
  source: string;
  confidence: number;
  x_line_count: number;
  y_line_count: number;
  error?: string | null;
  detail?: string | null;
};

export type AnalyzeRegionResult = {
  analysis: RegionStructuralAnalysis;
  compile_supported: boolean;
  compile_message?: string | null;
  ai_model?: string | null;
  pdf_grid?: PdfGridMeta | null;
  /** GPT JSON before server enrich (grid_lines merge, etc.) */
  vision_raw?: RegionStructuralAnalysis | Record<string, unknown> | null;
};

export type RegionAnalyzeDebug = {
  fetchedAt: string;
  ai_model: string | null;
  vision_raw: unknown;
  analysis_after_enrich: RegionStructuralAnalysis;
  full_api_response: AnalyzeRegionResult;
};

export type UniversalStructuralIntent = Record<string, unknown>;

export type RegionToIntentPreviewResult = {
  compile_mode: "explicit_layout" | "uniform_grid";
  intent: UniversalStructuralIntent;
  pure_preview?: UniversalStructuralIntent | null;
  column_count: number;
  compile_supported: boolean;
  compile_message?: string | null;
};

export type GridVertexDTO = {
  grid_index_x: number;
  grid_index_y: number;
  x_px: number;
  y_px: number;
};

export type RegionGridGeometryResult = {
  crop_width_px: number;
  crop_height_px: number;
  x_lines_px: number[];
  y_lines_px: number[];
  vertices: GridVertexDTO[];
  svg_markup: string;
  mm_per_px?: number | null;
  span_width_mm?: number | null;
  span_height_mm?: number | null;
  source: string;
  notes: string[];
  ok: boolean;
  error?: string | null;
};

export function gridVertexKey(ix: number, iy: number): string {
  return `${ix},${iy}`;
}

export type CropBoundsPt = {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

export type ColumnClick = {
  id: string;
  /** 0..1 relative to cropped viewport (authoritative for PDF mapping). */
  x_norm: number;
  y_norm: number;
  /** Pixel position on crop canvas (display). */
  x_px: number;
  y_px: number;
  /** Absolute PDF points when known. */
  x_pt?: number | null;
  y_pt?: number | null;
  mark?: string | null;
};

export type AlignedPin = {
  id: string;
  x_norm: number;
  y_norm: number;
  x_pt: number;
  y_pt: number;
  snapped_x_pt: number;
  snapped_y_pt: number;
  grid_index_x: number;
  grid_index_y: number;
  mark?: string | null;
};

export type RegionCropCalibrationResult = {
  crop_width_px: number;
  crop_height_px: number;
  mm_per_px?: number | null;
  mm_per_px_x?: number | null;
  mm_per_px_y?: number | null;
  span_width_mm?: number | null;
  span_height_mm?: number | null;
  x_grid_positions_mm?: number[];
  y_grid_positions_mm?: number[];
  grid_lines_x_px?: number[];
  grid_lines_y_px?: number[];
  suggested_column_profile?: string | null;
  grid_lines_x_pt?: number[];
  grid_lines_y_pt?: number[];
  crop_bounds_pt?: CropBoundsPt | null;
  vector_grid_source?: string;
  notes: string[];
};

export type RegionCropStep =
  | "upload"
  | "gallery"
  | "crop"
  | "grid-edit"
  | "grid"
  | "grid-review"
  | "review"
  | "viewer";
