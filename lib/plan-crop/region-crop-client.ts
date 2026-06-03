import type { GridModel } from "@/lib/plan-crop/grid-model";
import type {
  ActiveColumnIntersection,
  AnalyzeRegionResult,
  CropRectNorm,
  JsonValue,
  ColumnClick,
  RegionCropCalibrationResult,
  RegionGridGeometryResult,
  RegionStructuralAnalysis,
  RegionToIntentPreviewResult,
  UploadPdfResult,
  UniversalStructuralIntent,
} from "@/lib/plan-crop/types";

const DEFAULT_API_BASE = "http://localhost:8011";

const RAW_API_URL = process.env.NEXT_PUBLIC_CHAT_TO_IFC_API_URL?.trim();
const USE_DIRECT_PYTHON =
  process.env.NEXT_PUBLIC_CHAT_TO_IFC_DIRECT?.trim().toLowerCase() === "1" ||
  process.env.NEXT_PUBLIC_CHAT_TO_IFC_DIRECT?.trim().toLowerCase() === "true";

function normalizeApiBase(raw: string): string {
  const withProtocol = raw.match(/^https?:\/\//i) ? raw : `http://${raw}`;
  return withProtocol.replace(/\/$/, "");
}

export function resolveApiBase(): string {
  if (RAW_API_URL) {
    return normalizeApiBase(RAW_API_URL);
  }
  return DEFAULT_API_BASE;
}

function endpoint(path: string): string {
  if (USE_DIRECT_PYTHON && RAW_API_URL) {
    return `${resolveApiBase()}${path}`;
  }
  if (typeof window !== "undefined") {
    const proxyMap: Record<string, string> = {
      "/upload-pdf": "/api/upload-pdf",
      "/analyze-region": "/api/analyze-region",
      "/api/region-grid-geometry": "/api/region-grid-geometry",
      "/api/region-grid-finish": "/api/region-grid-finish",
      "/api/region-crop-calibration": "/api/region-crop-calibration",
      "/api/vector-grid-extract": "/api/vector-grid-extract",
      "/api/align-pins": "/api/align-pins",
      "/api/region-column-clicks-finish": "/api/region-column-clicks-finish",
      "/api/grid-model/extract": "/api/grid-model/extract",
      "/api/grid-model/finish": "/api/grid-model/finish",
      "/api/intent-to-ifc": "/api/intent-to-ifc",
      "/api/region-to-intent-preview": "/api/region-to-intent-preview",
      "/api/region-compile-ifc": "/api/region-compile-ifc",
      "/api/validate-universal-intent": "/api/validate-universal-intent",
    };
    const proxy = proxyMap[path] ?? path;
    return `${window.location.origin}${proxy}`;
  }
  return `${resolveApiBase()}${path}`;
}

export class RegionCropError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "RegionCropError";
    this.status = status;
  }
}

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: string;
      detail?: string | { message?: string };
      message?: string;
    };
    if (typeof payload.detail === "object" && payload.detail !== null) {
      return (payload.detail as { message?: string }).message ?? JSON.stringify(payload.detail);
    }
    return String(payload.detail ?? payload.error ?? payload.message ?? response.statusText);
  }
  const text = await response.text().catch(() => "");
  return text.trim() || response.statusText || "Request failed";
}

export async function fetchUploadPdf(file: File): Promise<UploadPdfResult> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(endpoint("/upload-pdf"), { method: "POST", body: form });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as UploadPdfResult;
}

export async function fetchAnalyzeRegion(options: {
  cropBlob: Blob;
  projectId?: string;
  pageIndex?: number;
  cropRectNorm?: CropRectNorm;
  scaleNote?: string;
}): Promise<AnalyzeRegionResult> {
  const form = new FormData();
  form.append("image", options.cropBlob, "crop.png");
  if (options.projectId) form.append("project_id", options.projectId);
  if (options.pageIndex != null) form.append("page_index", String(options.pageIndex));
  if (options.cropRectNorm) {
    form.append("crop_rect_norm", JSON.stringify(options.cropRectNorm));
  }
  if (options.scaleNote?.trim()) form.append("scale_note", options.scaleNote.trim());

  const response = await fetch(endpoint("/analyze-region"), { method: "POST", body: form });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as AnalyzeRegionResult;
}

export async function fetchRegionGridGeometry(options: {
  projectId: string;
  pageIndex: number;
  cropRectNorm: CropRectNorm;
  scaleNote?: string;
}): Promise<RegionGridGeometryResult> {
  const response = await fetch(endpoint("/api/region-grid-geometry"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: options.projectId,
      page_index: options.pageIndex,
      crop_rect_norm: options.cropRectNorm,
      scale_note: options.scaleNote?.trim() || null,
    }),
  });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as RegionGridGeometryResult;
}

export async function fetchRegionCropCalibration(options: {
  projectId: string;
  pageIndex: number;
  cropRectNorm: CropRectNorm;
  scaleNote?: string;
}): Promise<RegionCropCalibrationResult> {
  const response = await fetch(endpoint("/api/region-crop-calibration"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: options.projectId,
      page_index: options.pageIndex,
      crop_rect_norm: options.cropRectNorm,
      scale_note: options.scaleNote?.trim() || null,
    }),
  });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as RegionCropCalibrationResult;
}

export async function fetchGridModelExtract(options: {
  projectId: string;
  pageIndex: number;
  cropRectNorm: CropRectNorm;
  scaleNote?: string;
}): Promise<GridModel> {
  const response = await fetch(endpoint("/api/grid-model/extract"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: options.projectId,
      page_index: options.pageIndex,
      crop_rect_norm: options.cropRectNorm,
      scale_note: options.scaleNote?.trim() || null,
    }),
  });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as GridModel;
}

export async function fetchGridModelFinish(options: {
  gridModel: GridModel;
  columnProfile?: string;
  columnHeightMm?: number;
  parameterOverrides?: Record<string, JsonValue>;
}): Promise<AnalyzeRegionResult> {
  const profile =
    options.columnProfile?.trim() ||
    options.gridModel.suggested_column_profile?.trim() ||
    "HEB200";
  const response = await fetch(endpoint("/api/grid-model/finish"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grid_model: options.gridModel,
      column_profile: profile,
      column_height_mm: options.columnHeightMm ?? 6000,
      parameter_overrides: options.parameterOverrides ?? null,
    }),
  });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as AnalyzeRegionResult;
}

export async function fetchRegionColumnClicksFinish(options: {
  calibration: RegionCropCalibrationResult;
  clicks: ColumnClick[];
  projectId?: string;
  pageIndex?: number;
  cropRectNorm?: CropRectNorm;
  columnProfile?: string;
  columnHeightMm?: number;
  parameterOverrides?: Record<string, JsonValue>;
}): Promise<AnalyzeRegionResult> {
  const profile =
    options.columnProfile?.trim() ||
    options.calibration.suggested_column_profile?.trim() ||
    "HEB200";
  const response = await fetch(endpoint("/api/region-column-clicks-finish"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: options.projectId ?? null,
      page_index: options.pageIndex ?? null,
      crop_rect_norm: options.cropRectNorm ?? null,
      crop_width_px: options.calibration.crop_width_px,
      crop_height_px: options.calibration.crop_height_px,
      mm_per_px: options.calibration.mm_per_px ?? null,
      span_width_mm: options.calibration.span_width_mm ?? null,
      span_height_mm: options.calibration.span_height_mm ?? null,
      x_grid_positions_mm: options.calibration.x_grid_positions_mm ?? [],
      y_grid_positions_mm: options.calibration.y_grid_positions_mm ?? [],
      grid_lines_x_pt: options.calibration.grid_lines_x_pt ?? [],
      grid_lines_y_pt: options.calibration.grid_lines_y_pt ?? [],
      grid_lines_x_px: options.calibration.grid_lines_x_px ?? [],
      grid_lines_y_px: options.calibration.grid_lines_y_px ?? [],
      crop_bounds_pt: options.calibration.crop_bounds_pt ?? null,
      clicks: options.clicks.map((c) => ({
        x_norm: c.x_norm,
        y_norm: c.y_norm,
        x_pt: c.x_pt ?? null,
        y_pt: c.y_pt ?? null,
        x_px: c.x_px,
        y_px: c.y_px,
        mark: c.mark ?? null,
      })),
      column_profile: profile,
      column_height_mm: options.columnHeightMm ?? 6000,
      parameter_overrides: options.parameterOverrides ?? null,
    }),
  });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as AnalyzeRegionResult;
}

export async function fetchRegionGridFinish(options: {
  geometry: RegionGridGeometryResult;
  intersections: ActiveColumnIntersection[];
  columnProfile?: string;
  columnHeightMm?: number;
  parameterOverrides?: Record<string, JsonValue>;
}): Promise<AnalyzeRegionResult> {
  const response = await fetch(endpoint("/api/region-grid-finish"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      geometry: options.geometry,
      intersections: options.intersections,
      column_profile: options.columnProfile ?? "HEB200",
      column_height_mm: options.columnHeightMm ?? 6000,
      parameter_overrides: options.parameterOverrides ?? null,
    }),
  });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as AnalyzeRegionResult;
}

export async function fetchRegionToIntentPreview(
  analysis: RegionStructuralAnalysis,
  parameterOverrides?: Record<string, string | number | boolean | string[]>,
): Promise<RegionToIntentPreviewResult> {
  const response = await fetch(endpoint("/api/region-to-intent-preview"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      analysis,
      parameter_overrides: parameterOverrides ?? null,
    }),
  });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as RegionToIntentPreviewResult;
}

export async function fetchRegionCompileIfc(
  analysis: import("@/lib/plan-crop/types").RegionStructuralAnalysis,
  parameterOverrides?: Record<string, JsonValue>,
): Promise<{ blob: Blob; specSummary?: string; intentSummary?: string }> {
  const response = await fetch(endpoint("/api/region-compile-ifc"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/octet-stream" },
    body: JSON.stringify({
      analysis,
      parameter_overrides: parameterOverrides ?? null,
    }),
  });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  const blob = await response.blob();
  if (blob.size === 0) {
    throw new RegionCropError("Server returned an empty IFC file");
  }
  return {
    blob,
    specSummary: response.headers.get("X-Eyesteel-Spec")?.trim() || undefined,
    intentSummary: response.headers.get("X-Eyesteel-Intent")?.trim() || undefined,
  };
}

export async function fetchIntentToIfc(
  intent: UniversalStructuralIntent,
): Promise<{ blob: Blob; specSummary?: string; intentSummary?: string }> {
  const response = await fetch(endpoint("/api/intent-to-ifc"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/octet-stream" },
    body: JSON.stringify(intent),
  });
  if (!response.ok) {
    throw new RegionCropError(await readErrorMessage(response), response.status);
  }
  const blob = await response.blob();
  if (blob.size === 0) {
    throw new RegionCropError("Server returned an empty IFC file");
  }
  return {
    blob,
    specSummary: response.headers.get("X-Eyesteel-Spec")?.trim() || undefined,
    intentSummary: response.headers.get("X-Eyesteel-Intent")?.trim() || undefined,
  };
}
