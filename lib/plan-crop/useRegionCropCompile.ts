"use client";

import { useCallback, useRef } from "react";
import { createIfcObjectUrl, loadIfcBlobIntoViewer } from "@/lib/ai-designer/load-ifc-blob";
import {
  fetchRegionCompileIfc,
  fetchRegionToIntentPreview,
  RegionCropError,
} from "@/lib/plan-crop/region-crop-client";
import type {
  JsonValue,
  RegionStructuralAnalysis,
  UniversalStructuralIntent,
} from "@/lib/plan-crop/types";
import { analysisForCompile, parameterOverridesForCompile } from "@/lib/plan-crop/types";
import { IfcLoadError } from "@/lib/viewer/ifc-loader";
import type { ViewerEngine } from "@/lib/viewer/engine";

export function useRegionCropCompile() {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadIntentPreview = useCallback(
    async (
      analysis: RegionStructuralAnalysis,
      parameterOverrides: Record<string, JsonValue>,
    ) => {
      const overrides = parameterOverridesForCompile(parameterOverrides, analysis);
      const payload = analysisForCompile(analysis, overrides);
      return fetchRegionToIntentPreview(payload, overrides);
    },
    [],
  );

  const compileAndLoad = useCallback(
    async (
      analysis: RegionStructuralAnalysis,
      parameterOverrides: Record<string, JsonValue>,
      engine: ViewerEngine | null,
      onStatus?: (spec?: string, intentHdr?: string) => void,
    ) => {
      if (!engine) {
        throw new Error("Viewer engine not ready");
      }
      const overrides = parameterOverridesForCompile(parameterOverrides, analysis);
      const payload = analysisForCompile(analysis, overrides);
      const { blob, specSummary, intentSummary } = await fetchRegionCompileIfc(
        payload,
        overrides,
      );
      const objectUrl = createIfcObjectUrl(blob);
      try {
        await loadIfcBlobIntoViewer(engine, blob, objectUrl);
      } catch (err) {
        URL.revokeObjectURL(objectUrl);
        if (err instanceof IfcLoadError) throw err;
        throw err;
      }
      onStatus?.(specSummary, intentSummary);
      return { specSummary, intentSummary };
    },
    [],
  );

  return { loadIntentPreview, compileAndLoad };
}
