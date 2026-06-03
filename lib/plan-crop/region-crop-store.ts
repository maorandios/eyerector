import { create } from "zustand";
import type { GridModel } from "@/lib/plan-crop/grid-model";
import type {
  AnalyzeRegionResult,
  ColumnClick,
  CropRectNorm,
  JsonValue,
  PageAsset,
  RegionAnalyzeDebug,
  RegionCropCalibrationResult,
  RegionCropStep,
  RegionStructuralAnalysis,
  UniversalStructuralIntent,
} from "@/lib/plan-crop/types";
import { snapColumnClicks, type SnappedColumn } from "@/lib/plan-crop/grid-snap";
import { he } from "@/lib/i18n/he";
import {
  estimateColumnCount,
  gridStationsFromEdited,
  parametersToRecord,
} from "@/lib/plan-crop/types";

type RegionCropState = {
  step: RegionCropStep;
  projectId: string | null;
  filename: string | null;
  pages: PageAsset[];
  baseUrl: string | null;
  selectedPageIndex: number | null;
  cropRectNorm: CropRectNorm | null;
  scaleNote: string;
  analysis: RegionStructuralAnalysis | null;
  compileSupported: boolean;
  compileMessage: string | null;
  compileMode: "explicit_layout" | "uniform_grid" | null;
  columnCount: number;
  editedParameters: Record<string, JsonValue>;
  universalIntentPreview: UniversalStructuralIntent | null;
  statusText: string;
  error: string;
  isLoading: boolean;
  hasModel: boolean;
  analyzeDebug: RegionAnalyzeDebug | null;
  cropCalibration: RegionCropCalibrationResult | null;
  columnClicks: ColumnClick[];
  snappedColumns: SnappedColumn[];
  cropPreviewUrl: string | null;
  gridModel: GridModel | null;
  setGridModel: (model: GridModel | null) => void;
  setStep: (step: RegionCropStep) => void;
  setUploadResult: (payload: {
    project_id: string;
    filename: string;
    pages: PageAsset[];
    base_url: string;
  }) => void;
  selectPage: (pageIndex: number) => void;
  setCropRect: (rect: CropRectNorm | null) => void;
  setScaleNote: (note: string) => void;
  setAnalysisResult: (result: AnalyzeRegionResult) => void;
  patchParameter: (key: string, value: JsonValue) => void;
  setEditedParameters: (params: Record<string, JsonValue>) => void;
  setIntentPreview: (intent: UniversalStructuralIntent | null) => void;
  setCompileMeta: (supported: boolean, message: string | null) => void;
  setPreviewMeta: (
    mode: "explicit_layout" | "uniform_grid",
    columnCount: number,
    supported: boolean,
    message: string | null,
  ) => void;
  setStatusText: (text: string) => void;
  setError: (text: string) => void;
  setIsLoading: (loading: boolean) => void;
  setHasModel: (has: boolean) => void;
  setGridModelReady: (model: GridModel, previewUrl: string) => void;
  setColumnMarkingReady: (cal: RegionCropCalibrationResult, previewUrl: string) => void;
  setCropPreviewUrl: (url: string | null) => void;
  addColumnClick: (click: ColumnClick) => void;
  removeColumnClick: (id: string) => void;
  undoLastColumnClick: () => void;
  clearColumnClicks: () => void;
  goToGridReview: () => void;
  reset: () => void;
};

const initialState = {
  step: "upload" as RegionCropStep,
  projectId: null,
  filename: null,
  pages: [] as PageAsset[],
  baseUrl: null,
  selectedPageIndex: null,
  cropRectNorm: null,
  scaleNote: "units mm",
  analysis: null,
  compileSupported: false,
  compileMessage: null,
  compileMode: null as "explicit_layout" | "uniform_grid" | null,
  columnCount: 0,
  editedParameters: {} as Record<string, JsonValue>,
  universalIntentPreview: null,
  statusText: "",
  error: "",
  isLoading: false,
  hasModel: false,
  analyzeDebug: null as RegionAnalyzeDebug | null,
  cropCalibration: null as RegionCropCalibrationResult | null,
  columnClicks: [] as ColumnClick[],
  snappedColumns: [] as SnappedColumn[],
  cropPreviewUrl: null as string | null,
  gridModel: null as GridModel | null,
};

export const useRegionCropStore = create<RegionCropState>((set) => ({
  ...initialState,
  setStep: (step) => set({ step }),
  setUploadResult: (payload) =>
    set({
      projectId: payload.project_id,
      filename: payload.filename,
      pages: payload.pages,
      baseUrl: payload.base_url,
      step: "gallery",
      error: "",
    }),
  selectPage: (pageIndex) =>
    set({
      selectedPageIndex: pageIndex,
      cropRectNorm: null,
      step: "crop",
      analysis: null,
      editedParameters: {},
      universalIntentPreview: null,
      compileSupported: false,
      compileMessage: null,
      analyzeDebug: null,
      cropCalibration: null,
      columnClicks: [],
      snappedColumns: [],
      cropPreviewUrl: null,
      error: "",
    }),
  setCropRect: (rect) => set({ cropRectNorm: rect }),
  setScaleNote: (note) => set({ scaleNote: note }),
  setAnalysisResult: (result) => {
    const edited = parametersToRecord(result.analysis.detected_parameters);
    for (const entry of result.analysis.column_profile_by_mark ?? []) {
      const mark = entry.mark?.trim();
      const profile = entry.profile_name?.trim();
      if (mark && profile) {
        edited[mark] = profile;
      }
    }
    for (const hit of result.analysis.active_column_intersections ?? []) {
      const mark = hit.mark?.trim();
      const profile = hit.profile_name?.trim();
      if (mark && profile) {
        edited[mark] = profile;
      }
    }
    const { xs: gridXs, ys: gridYs } = gridStationsFromEdited(edited, result.analysis);
    if (gridXs.length >= 2) {
      edited.grid_lines_x_mm = gridXs.join(", ");
    } else if (result.analysis.x_grid_positions_mm?.length) {
      edited.grid_lines_x_mm = result.analysis.x_grid_positions_mm.join(", ");
    }
    if (gridYs.length >= 2) {
      edited.grid_lines_y_mm = gridYs.join(", ");
    } else if (result.analysis.y_grid_positions_mm?.length) {
      edited.grid_lines_y_mm = result.analysis.y_grid_positions_mm.join(", ");
    }
    if (result.analysis.x_bay_spacings_mm?.length) {
      edited.x_bay_spacings_mm = result.analysis.x_bay_spacings_mm.join(", ");
    }
    if (result.analysis.y_bay_spacings_mm?.length) {
      edited.y_bay_spacings_mm = result.analysis.y_bay_spacings_mm.join(", ");
    }
    if (result.pdf_grid?.applied) {
      edited.grid_extraction_source = `pdf_hybrid;conf=${result.pdf_grid.confidence.toFixed(2)}`;
    } else if (result.pdf_grid?.attempted && result.pdf_grid.error) {
      edited.grid_extraction_source = `pdf_failed:${result.pdf_grid.error}`;
    }
    const colCount = estimateColumnCount(result.analysis);
    const debug: RegionAnalyzeDebug = {
      fetchedAt: new Date().toISOString(),
      ai_model: result.ai_model ?? null,
      vision_raw: result.vision_raw ?? null,
      analysis_after_enrich: result.analysis,
      full_api_response: result,
    };
    const statusText =
      result.pdf_grid?.applied
        ? `${he.planCropAnalyzeOk} — PDF grid X=${result.pdf_grid.x_line_count} Y=${result.pdf_grid.y_line_count}`
        : he.planCropAnalyzeOk;
    if (typeof console !== "undefined" && console.groupCollapsed) {
      console.groupCollapsed("[plan-crop] analyze-region debug");
      console.log("vision_raw (GPT)", result.vision_raw);
      console.log("analysis (after enrich)", result.analysis);
      console.log("full response", result);
      console.groupEnd();
    }
    set({
      analysis: result.analysis,
      compileSupported: result.compile_supported,
      compileMessage: result.compile_message ?? null,
      compileMode: colCount > 0 ? "explicit_layout" : null,
      columnCount: colCount,
      editedParameters: edited,
      analyzeDebug: debug,
      statusText,
      step: "review",
      error: "",
    });
  },
  patchParameter: (key, value) =>
    set((s) => ({
      editedParameters: { ...s.editedParameters, [key]: value },
    })),
  setEditedParameters: (params) => set({ editedParameters: params }),
  setIntentPreview: (intent) => set({ universalIntentPreview: intent }),
  setCompileMeta: (supported, message) =>
    set({ compileSupported: supported, compileMessage: message }),
  setPreviewMeta: (mode, columnCount, supported, message) =>
    set({
      compileMode: mode,
      columnCount,
      compileSupported: supported,
      compileMessage: message,
    }),
  setStatusText: (text) => set({ statusText: text }),
  setError: (text) => set({ error: text }),
  setIsLoading: (loading) => set({ isLoading: loading }),
  setHasModel: (has) => set({ hasModel: has }),
  setGridModel: (model) => set({ gridModel: model }),
  setGridModelReady: (model, previewUrl) => {
    const edited: Record<string, JsonValue> = {};
    if (model.suggested_column_profile?.trim()) {
      edited.column_profile = model.suggested_column_profile.trim();
    }
    return set({
      gridModel: model,
      cropPreviewUrl: previewUrl,
      columnClicks: [],
      snappedColumns: [],
      cropCalibration: null,
      editedParameters: edited,
      step: "grid-edit",
      error: "",
      statusText: he.planCropExtractGridOk,
    });
  },
  setColumnMarkingReady: (cal, previewUrl) => {
    const edited: Record<string, JsonValue> = {};
    if (cal.suggested_column_profile?.trim()) {
      edited.column_profile = cal.suggested_column_profile.trim();
    }
    return set({
      cropCalibration: cal,
      cropPreviewUrl: previewUrl,
      columnClicks: [],
      snappedColumns: [],
      editedParameters: edited,
      step: "grid",
      error: "",
      statusText: cal.suggested_column_profile
        ? `${he.planCropMarkColumnsOk} — ${cal.suggested_column_profile}`
        : he.planCropMarkColumnsOk,
    });
  },
  setCropPreviewUrl: (url) => set({ cropPreviewUrl: url }),
  addColumnClick: (click) =>
    set((s) => ({ columnClicks: [...s.columnClicks, click] })),
  removeColumnClick: (id) =>
    set((s) => ({ columnClicks: s.columnClicks.filter((c) => c.id !== id) })),
  undoLastColumnClick: () =>
    set((s) => ({ columnClicks: s.columnClicks.slice(0, -1) })),
  clearColumnClicks: () => set({ columnClicks: [], snappedColumns: [] }),
  goToGridReview: () =>
    set((s) => {
      if (!s.cropCalibration || s.columnClicks.length === 0) {
        return { error: he.planCropGridReviewNeedClicks };
      }
      const snapped = snapColumnClicks(s.cropCalibration, s.columnClicks);
      if (snapped.length !== s.columnClicks.length) {
        return { error: he.planCropGridReviewNoPdfBays };
      }
      return {
        snappedColumns: snapped,
        step: "grid-review" as RegionCropStep,
        error: "",
        statusText: he.planCropGridReviewReady,
      };
    }),
  reset: () => {
    const prev = useRegionCropStore.getState().cropPreviewUrl;
    if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
    set({ ...initialState });
  },
}));
