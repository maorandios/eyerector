"use client";

import Link from "next/link";
import { useCallback, useMemo, useRef, useState } from "react";
import { ArrowRight, FileUp, Undo2 } from "lucide-react";
import { AiDesignerViewport } from "@/components/ai-designer/AiDesignerViewport";
import { AiLoadingOverlay } from "@/components/ai-designer/AiLoadingOverlay";
import { PdfPageGallery } from "@/components/plan-crop/PdfPageGallery";
import { RegionAnalysisForm } from "@/components/plan-crop/RegionAnalysisForm";
import { GridMarkupCanvas } from "@/components/plan-crop/GridMarkupCanvas";
import { GridMarkupReviewPanel } from "@/components/plan-crop/GridMarkupReviewPanel";
import { GridModelEditor, GridModelPanel } from "@/components/plan-crop/GridModelEditor";
import { RegionGridOverlay } from "@/components/plan-crop/RegionGridOverlay";
import { RegionCropCanvas } from "@/components/plan-crop/RegionCropCanvas";
import { Button } from "@/components/ui/button";
import { cropImageToBlob, resolveAssetUrl } from "@/lib/plan-crop/crop-image";
import {
  fetchAnalyzeRegion,
  fetchGridModelExtract,
  fetchGridModelFinish,
  fetchRegionColumnClicksFinish,
  fetchRegionCropCalibration,
  fetchUploadPdf,
  RegionCropError,
  resolveApiBase,
} from "@/lib/plan-crop/region-crop-client";
import { clicksForFinish } from "@/lib/plan-crop/grid-snap";
import { useRegionCropStore } from "@/lib/plan-crop/region-crop-store";
import { useRegionCropCompile } from "@/lib/plan-crop/useRegionCropCompile";
import { he } from "@/lib/i18n/he";
import { IfcLoadError } from "@/lib/viewer/ifc-loader";
import type { ViewerEngine } from "@/lib/viewer/engine";

export function RegionCropWorkspace() {
  const engineRef = useRef<ViewerEngine | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    step,
    projectId,
    filename,
    pages,
    selectedPageIndex,
    cropRectNorm,
    scaleNote,
    analysis,
    compileSupported,
    compileMessage,
    editedParameters,
    statusText,
    error,
    isLoading,
    hasModel,
    setUploadResult,
    selectPage,
    setCropRect,
    setScaleNote,
    setAnalysisResult,
    patchParameter,
    setCompileMeta,
    setPreviewMeta,
    columnCount,
    compileMode,
    analyzeDebug,
    cropCalibration,
    columnClicks,
    snappedColumns,
    cropPreviewUrl,
    gridModel,
    setGridModel,
    setGridModelReady,
    setColumnMarkingReady,
    addColumnClick,
    removeColumnClick,
    undoLastColumnClick,
    goToGridReview,
    setStatusText,
    setError,
    setIsLoading,
    setHasModel,
    setStep,
  } = useRegionCropStore();

  const { loadIntentPreview, compileAndLoad } = useRegionCropCompile();
  const apiBase = resolveApiBase();
  const [selectedColumnId, setSelectedColumnId] = useState<string | null>(null);

  const resolveUrl = useCallback(
    (path: string) => resolveAssetUrl(path, apiBase),
    [apiBase],
  );

  const selectedPage = useMemo(
    () => pages.find((p) => p.page_index === selectedPageIndex) ?? null,
    [pages, selectedPageIndex],
  );

  const pageImageUrl = selectedPage ? resolveUrl(selectedPage.url) : "";

  const handleEngineReady = useCallback((engine: ViewerEngine | null) => {
    engineRef.current = engine;
  }, []);

  const handleFileChange = useCallback(
    async (file: File | null) => {
      if (!file || isLoading) return;
      setError("");
      setIsLoading(true);
      try {
        const result = await fetchUploadPdf(file);
        setUploadResult(result);
        setStatusText(`${he.planCropUploadOk} (${result.page_count} ${he.planCropPages})`);
      } catch (err) {
        setError(err instanceof RegionCropError ? err.message : he.planCropError);
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, setError, setIsLoading, setStatusText, setUploadResult],
  );

  const handleExtractGrid = useCallback(async () => {
    if (!cropRectNorm || !selectedPage || !projectId || isLoading) return;
    setError("");
    setIsLoading(true);
    try {
      const blob = await cropImageToBlob(pageImageUrl, cropRectNorm);
      if (cropPreviewUrl?.startsWith("blob:")) URL.revokeObjectURL(cropPreviewUrl);
      const previewUrl = URL.createObjectURL(blob);
      const model = await fetchGridModelExtract({
        projectId,
        pageIndex: selectedPage.page_index,
        cropRectNorm,
        scaleNote,
      });
      setGridModelReady(model, previewUrl);
      setSelectedColumnId(null);
    } catch (err) {
      setError(err instanceof RegionCropError ? err.message : he.planCropError);
    } finally {
      setIsLoading(false);
    }
  }, [
    cropPreviewUrl,
    cropRectNorm,
    isLoading,
    pageImageUrl,
    projectId,
    scaleNote,
    selectedPage,
    setGridModelReady,
    setError,
    setIsLoading,
  ]);

  const handleApproveGridModel = useCallback(async () => {
    if (!gridModel || gridModel.columns.length === 0 || isLoading) return;
    setError("");
    setIsLoading(true);
    try {
      const profile =
        typeof editedParameters.column_profile === "string"
          ? editedParameters.column_profile
          : "HEB200";
      const result = await fetchGridModelFinish({
        gridModel,
        columnProfile: profile,
        parameterOverrides: editedParameters,
      });
      setAnalysisResult(result);
    } catch (err) {
      setError(err instanceof RegionCropError ? err.message : he.planCropError);
    } finally {
      setIsLoading(false);
    }
  }, [gridModel, editedParameters, isLoading, setAnalysisResult, setError, setIsLoading]);

  const handleMarkColumns = useCallback(async () => {
    if (!cropRectNorm || !selectedPage || !projectId || isLoading) return;
    setError("");
    setIsLoading(true);
    try {
      const blob = await cropImageToBlob(pageImageUrl, cropRectNorm);
      if (cropPreviewUrl?.startsWith("blob:")) URL.revokeObjectURL(cropPreviewUrl);
      const previewUrl = URL.createObjectURL(blob);
      const cal = await fetchRegionCropCalibration({
        projectId,
        pageIndex: selectedPage.page_index,
        cropRectNorm,
        scaleNote,
      });
      setColumnMarkingReady(cal, previewUrl);
    } catch (err) {
      setError(err instanceof RegionCropError ? err.message : he.planCropError);
    } finally {
      setIsLoading(false);
    }
  }, [
    cropPreviewUrl,
    cropRectNorm,
    isLoading,
    pageImageUrl,
    projectId,
    scaleNote,
    selectedPage,
    setColumnMarkingReady,
    setError,
    setIsLoading,
  ]);

  const handleApproveGrid = useCallback(async () => {
    if (!cropCalibration || columnClicks.length === 0 || isLoading) return;
    setError("");
    setIsLoading(true);
    try {
      const profile =
        typeof editedParameters.column_profile === "string"
          ? editedParameters.column_profile
          : "HEB200";
      const result = await fetchRegionColumnClicksFinish({
        calibration: cropCalibration,
        clicks: clicksForFinish(columnClicks, snappedColumns, cropCalibration),
        projectId: projectId ?? undefined,
        pageIndex: selectedPage?.page_index,
        cropRectNorm: cropRectNorm ?? undefined,
        columnProfile: profile,
        parameterOverrides: editedParameters,
      });
      setAnalysisResult(result);
    } catch (err) {
      setError(err instanceof RegionCropError ? err.message : he.planCropError);
    } finally {
      setIsLoading(false);
    }
  }, [
    columnClicks,
    snappedColumns,
    cropCalibration,
    cropRectNorm,
    projectId,
    selectedPage,
    editedParameters,
    isLoading,
    setAnalysisResult,
    setError,
    setIsLoading,
  ]);

  const handleAnalyzeCrop = useCallback(async () => {
    if (!cropRectNorm || !selectedPage || !projectId || isLoading) return;
    setError("");
    setIsLoading(true);
    try {
      const blob = await cropImageToBlob(pageImageUrl, cropRectNorm);
      const result = await fetchAnalyzeRegion({
        cropBlob: blob,
        projectId,
        pageIndex: selectedPage.page_index,
        cropRectNorm,
        scaleNote,
      });
      setAnalysisResult(result);
    } catch (err) {
      setError(err instanceof RegionCropError ? err.message : he.planCropError);
    } finally {
      setIsLoading(false);
    }
  }, [
    cropRectNorm,
    isLoading,
    pageImageUrl,
    projectId,
    scaleNote,
    selectedPage,
    setAnalysisResult,
    setError,
    setIsLoading,
    setStatusText,
  ]);

  const refreshIntentPreview = useCallback(async () => {
    if (!analysis) return;
    setIsLoading(true);
    setError("");
    try {
      const preview = await loadIntentPreview(analysis, editedParameters);
      setPreviewMeta(
        preview.compile_mode,
        preview.column_count,
        preview.compile_supported,
        preview.compile_message ?? null,
      );
      if (!preview.compile_supported) {
        setError(preview.compile_message ?? he.planCropCompileBlocked);
      } else if (preview.compile_mode === "explicit_layout") {
        setStatusText(
          `${he.planCropExplicitLayout} (${preview.column_count} ${he.planCropColumns})`,
        );
      }
    } catch (err) {
      setError(err instanceof RegionCropError ? err.message : he.planCropError);
    } finally {
      setIsLoading(false);
    }
  }, [
    analysis,
    editedParameters,
    loadIntentPreview,
    setPreviewMeta,
    setError,
    setIsLoading,
    setStatusText,
  ]);

  const handleBuild3d = useCallback(async () => {
    if (!analysis || isLoading) return;
    setError("");
    setIsLoading(true);
    setStep("viewer");
    try {
      const engine = engineRef.current;
      if (!engine) {
        throw new Error(he.aiDesignerViewerNotReady);
      }
      const { specSummary, intentSummary } = await compileAndLoad(
        analysis,
        editedParameters,
        engine,
        (spec, hdr) => {
          setStatusText([spec, hdr].filter(Boolean).join(" · ") || he.planCropBuildOk);
        },
      );
      setHasModel(true);
      if (specSummary || intentSummary) {
        setStatusText([specSummary, intentSummary].filter(Boolean).join(" · "));
      }
    } catch (err) {
      if (err instanceof RegionCropError || err instanceof IfcLoadError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(he.planCropError);
      }
    } finally {
      setIsLoading(false);
    }
  }, [
    analysis,
    compileAndLoad,
    editedParameters,
    isLoading,
    setError,
    setHasModel,
    setIsLoading,
    setStatusText,
    setStep,
    analysis,
  ]);

  return (
    <div className="flex h-dvh flex-col lg:flex-row">
      <aside className="safe-top safe-bottom flex max-h-[50vh] shrink-0 flex-col gap-3 overflow-y-auto border-b border-slate-800 bg-slate-950 p-4 lg:max-h-none lg:max-w-md lg:flex-1 lg:border-b-0 lg:border-e">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h1 className="text-lg font-semibold text-slate-100">{he.planCropTitle}</h1>
            <p className="text-xs text-slate-400">{he.planCropSubtitle}</p>
          </div>
          <Link
            href="/"
            className="flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200"
          >
            <ArrowRight className="h-4 w-4" />
            {he.aiDesignerBackHome}
          </Link>
        </div>

        {step === "upload" && (
          <div className="flex flex-col gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                void handleFileChange(f);
                e.target.value = "";
              }}
            />
            <Button
              type="button"
              variant="secondary"
              className="w-full"
              disabled={isLoading}
              onClick={() => fileInputRef.current?.click()}
            >
              <FileUp className="me-2 h-4 w-4" />
              {he.planCropSelectPdf}
            </Button>
          </div>
        )}

        {(step === "gallery" ||
          step === "crop" ||
          step === "grid-edit" ||
          step === "grid-review" ||
          step === "review" ||
          step === "viewer") &&
          pages.length > 0 && (
            <PdfPageGallery
              pages={pages}
              resolveUrl={resolveUrl}
              selectedPageIndex={selectedPageIndex}
              onSelect={selectPage}
            />
          )}

        {filename ? (
          <p className="truncate text-xs text-slate-500">
            {filename}
            {projectId ? ` · ${projectId.slice(0, 8)}` : ""}
          </p>
        ) : null}

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-400">{he.planImportScaleLabel}</span>
          <input
            className="rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100"
            value={scaleNote}
            onChange={(e) => setScaleNote(e.target.value)}
            placeholder={he.planImportScalePlaceholder}
          />
        </label>

        {(step === "crop" || step === "review") && selectedPage && pageImageUrl ? (
          <RegionCropCanvas
            imageUrl={pageImageUrl}
            cropRect={cropRectNorm}
            onCropChange={setCropRect}
          />
        ) : null}

        {step === "crop" && cropRectNorm ? (
          <div className="flex flex-col gap-2">
            <Button
              type="button"
              disabled={isLoading || !projectId}
              onClick={() => void handleExtractGrid()}
              className="bg-[#00ffcc] text-slate-950 hover:bg-[#00e6b8]"
            >
              {isLoading ? he.planCropExtractingGrid : he.planCropExtractGrid}
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={isLoading || !projectId}
              onClick={() => void handleMarkColumns()}
            >
              {he.planCropMarkColumnsLegacy}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={isLoading}
              onClick={() => void handleAnalyzeCrop()}
            >
              {isLoading ? he.planCropAnalyzing : he.planCropAnalyze}
            </Button>
          </div>
        ) : null}

        {step === "grid-edit" && gridModel ? (
          <GridModelPanel
            model={gridModel}
            onChange={setGridModel}
            selectedId={selectedColumnId}
            onSelect={setSelectedColumnId}
            isLoading={isLoading}
            onBack={() => setStep("crop")}
            onApprove={() => void handleApproveGridModel()}
          />
        ) : null}

        {step === "grid" && cropCalibration ? (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-slate-400">{he.planCropColumnClickHint}</p>
            <p className="text-xs text-slate-500">
              {columnClicks.length} {he.planCropColumns}
            </p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={columnClicks.length === 0}
              onClick={undoLastColumnClick}
            >
              <Undo2 className="me-1 h-4 w-4" />
              {he.planCropUndoClick}
            </Button>
            <Button
              type="button"
              disabled={isLoading || columnClicks.length === 0}
              onClick={() => goToGridReview()}
              className="bg-[#00ffcc] text-slate-950 hover:bg-[#00e6b8]"
            >
              {he.planCropGridContinue}
            </Button>
            <Button type="button" variant="ghost" disabled={isLoading} onClick={() => setStep("crop")}>
              {he.planCropBackToCrop}
            </Button>
          </div>
        ) : null}

        {step === "grid-review" && cropCalibration ? (
          <GridMarkupReviewPanel
            calibration={cropCalibration}
            snapped={snappedColumns}
            clickCount={columnClicks.length}
            isLoading={isLoading}
            onBack={() => setStep("grid")}
            onApprove={() => void handleApproveGrid()}
          />
        ) : null}

        {step === "review" && analysis ? (
          <RegionAnalysisForm
            analysis={analysis}
            editedParameters={editedParameters}
            compileSupported={compileSupported}
            compileMessage={compileMessage}
            compileMode={compileMode}
            columnCount={columnCount}
            isLoading={isLoading}
            onPatch={patchParameter}
            onPreview={() => void refreshIntentPreview()}
            onBuild3d={() => void handleBuild3d()}
            analyzeDebug={analyzeDebug}
            pdfGrid={analyzeDebug?.full_api_response?.pdf_grid ?? null}
            aiModel={analyzeDebug?.ai_model ?? null}
          />
        ) : null}

        {statusText ? <p className="text-xs text-emerald-400/90">{statusText}</p> : null}
        {error ? <p className="text-sm text-red-400">{error}</p> : null}
      </aside>

      <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        {step === "grid-edit" && gridModel && cropPreviewUrl ? (
          <GridModelEditor
            className="flex min-h-0 flex-1 flex-col bg-slate-950 p-3"
            cropImageUrl={cropPreviewUrl}
            model={gridModel}
            onChange={setGridModel}
            selectedId={selectedColumnId}
            onSelect={setSelectedColumnId}
          />
        ) : null}
        {(step === "grid" || step === "grid-review") &&
        cropCalibration &&
        cropPreviewUrl ? (
          <GridMarkupCanvas
            className="flex min-h-0 flex-1 flex-col bg-slate-950 p-3"
            cropImageUrl={cropPreviewUrl}
            calibration={cropCalibration}
            clicks={columnClicks}
            snapped={step === "grid-review" ? snappedColumns : []}
            mode={step === "grid-review" ? "review" : "mark"}
            onAddClick={step === "grid" ? addColumnClick : undefined}
            onRemoveClick={step === "grid" ? removeColumnClick : undefined}
          />
        ) : null}
        {step === "review" && analysis && cropRectNorm && pageImageUrl ? (
          <div className="absolute inset-x-0 top-0 z-10 max-h-[45vh] shrink-0 overflow-y-auto p-3">
            <RegionGridOverlay
              imageUrl={pageImageUrl}
              cropRect={cropRectNorm}
              analysis={analysis}
              editedParameters={editedParameters}
            />
          </div>
        ) : null}
        {step !== "grid" && step !== "grid-review" && step !== "grid-edit" ? (
          <AiDesignerViewport
            className="min-h-0 flex-1"
            onEngineReady={handleEngineReady}
            hasModel={hasModel}
            placeholderMessage={he.planCropViewportWaiting}
          />
        ) : null}
        <AiLoadingOverlay visible={isLoading} />
      </section>
    </div>
  );
}
