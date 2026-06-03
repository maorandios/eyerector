"use client";

import { Button } from "@/components/ui/button";
import { he } from "@/lib/i18n/he";
import { RegionAnalyzeDebugPanel } from "@/components/plan-crop/RegionAnalyzeDebugPanel";
import type {
  JsonValue,
  PdfGridMeta,
  RegionAnalyzeDebug,
  RegionStructuralAnalysis,
} from "@/lib/plan-crop/types";
import { gridStationsFromEdited } from "@/lib/plan-crop/types";
import { cn } from "@/lib/utils";

type RegionAnalysisFormProps = {
  analysis: RegionStructuralAnalysis;
  editedParameters: Record<string, JsonValue>;
  compileSupported: boolean;
  compileMessage: string | null;
  compileMode: "explicit_layout" | "uniform_grid" | null;
  columnCount: number;
  isLoading: boolean;
  onPatch: (key: string, value: JsonValue) => void;
  onPreview: () => void;
  onBuild3d: () => void;
  analyzeDebug?: RegionAnalyzeDebug | null;
  pdfGrid?: PdfGridMeta | null;
  aiModel?: string | null;
};

function formatElementType(type: string): string {
  const map: Record<string, string> = {
    grid: he.planCropTypeGrid,
    truss: he.planCropTypeTruss,
    mezzanine: he.planCropTypeMezzanine,
    staircase: he.planCropTypeStaircase,
    unknown: he.planCropTypeUnknown,
  };
  return map[type] ?? type;
}

export function RegionAnalysisForm({
  analysis,
  editedParameters,
  compileSupported,
  compileMessage,
  compileMode,
  columnCount,
  isLoading,
  onPatch,
  onPreview,
  onBuild3d,
  analyzeDebug,
  pdfGrid,
  aiModel,
}: RegionAnalysisFormProps) {
  const lowConfidence = analysis.confidence < 0.6;
  const keys = Object.keys(editedParameters);
  const { xs, ys } = gridStationsFromEdited(editedParameters, analysis);
  const gridSource = String(editedParameters.grid_extraction_source ?? "");

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-slate-700 bg-slate-900/80 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs text-slate-400">{he.planCropDetectedType}</p>
          <p className="text-lg font-medium text-[#00ffcc]">
            {formatElementType(analysis.element_type)}
          </p>
        </div>
        <div
          className={cn(
            "rounded-full px-3 py-1 text-sm font-medium",
            lowConfidence ? "bg-amber-900/50 text-amber-200" : "bg-emerald-900/40 text-emerald-200",
          )}
        >
          {(analysis.confidence * 100).toFixed(0)}%
        </div>
      </div>

      {aiModel ? (
        <p className="text-xs text-slate-500">
          Model: <span className="text-slate-300">{aiModel}</span>
        </p>
      ) : null}
      {pdfGrid?.attempted ? (
        <p
          className={cn(
            "rounded border px-2 py-1.5 text-xs",
            pdfGrid.applied
              ? "border-emerald-700/60 bg-emerald-950/40 text-emerald-200"
              : "border-amber-700/60 bg-amber-950/40 text-amber-200",
          )}
        >
          {pdfGrid.applied ? he.planCropPdfGridApplied : he.planCropPdfGridFailed}
          {" · "}
          {he.planCropGridLineCounts}: X={pdfGrid.x_line_count || xs.length}, Y=
          {pdfGrid.y_line_count || ys.length}
          {pdfGrid.detail ? ` — ${pdfGrid.detail}` : ""}
          {pdfGrid.error ? ` (${pdfGrid.error})` : ""}
        </p>
      ) : (
        <p className="text-xs text-slate-600">{he.planCropPdfGridSkipped}</p>
      )}
      {gridSource ? (
        <p className="text-xs text-slate-500">
          grid_extraction_source: <span className="text-slate-300">{gridSource}</span>
        </p>
      ) : null}
      {analysis.element_type === "grid" ? (
        <p className="text-xs text-slate-500">{he.planCropGridHint}</p>
      ) : null}
      {compileMode === "explicit_layout" && columnCount > 0 ? (
        <p className="text-xs text-emerald-400/90">
          {he.planCropExplicitLayout}: {columnCount} {he.planCropColumns}
          {analysis.layout_mode === "sparse_intersections" ||
          (analysis.active_column_intersections?.length ?? 0) > 0
            ? ` (${he.planCropSparseLayout})`
            : ""}
        </p>
      ) : null}
      {analysis.notes ? (
        <p className="text-sm text-slate-400">{analysis.notes}</p>
      ) : null}
      {compileMessage ? (
        <p className="text-sm text-amber-300">{compileMessage}</p>
      ) : null}

      {analyzeDebug ? <RegionAnalyzeDebugPanel debug={analyzeDebug} /> : null}

      {keys.length > 0 ? (
        <div className="max-h-[28vh] space-y-2 overflow-y-auto">
          {keys.map((key) => {
            const val = editedParameters[key];
            const isNumber =
              typeof val === "number" ||
              (typeof val === "string" && /^-?\d+(\.\d+)?$/.test(val.trim()));
            return (
              <label key={key} className="flex flex-col gap-1 text-sm">
                <span className="text-slate-400">{key}</span>
                <input
                  type={isNumber ? "number" : "text"}
                  className="rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-slate-100"
                  value={Array.isArray(val) ? val.join(", ") : String(val ?? "")}
                  onChange={(e) => {
                    const raw = e.target.value;
                    const isGridLines = key.startsWith("grid_lines_");
                    if (isNumber) {
                      const n = parseFloat(raw);
                      onPatch(key, Number.isFinite(n) ? n : raw);
                    } else if (isGridLines || raw.includes(",")) {
                      onPatch(key, raw);
                    } else {
                      onPatch(key, raw);
                    }
                  }}
                />
              </label>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-slate-500">{he.planCropNoParameters}</p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" disabled={isLoading} onClick={onPreview}>
          {he.planCropPreviewIntent}
        </Button>
        <Button
          type="button"
          disabled={isLoading || !compileSupported}
          onClick={onBuild3d}
          className="bg-[#00ffcc] text-slate-950 hover:bg-[#00e6b8]"
        >
          {he.planCropBuild3d}
        </Button>
      </div>
    </div>
  );
}
