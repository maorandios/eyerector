"use client";

import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { ArrowRight, FileUp } from "lucide-react";
import { AiDesignerViewport } from "@/components/ai-designer/AiDesignerViewport";
import { AiLoadingOverlay } from "@/components/ai-designer/AiLoadingOverlay";
import { Button } from "@/components/ui/button";
import { he } from "@/lib/i18n/he";
import { createIfcObjectUrl, loadIfcBlobIntoViewer } from "@/lib/ai-designer/load-ifc-blob";
import {
  PdfPlanError,
  fetchPdfToIfc,
  fetchPdfToStructuralJson,
} from "@/lib/ai-designer/pdf-plan-client";
import { IfcLoadError } from "@/lib/viewer/ifc-loader";
import type { ViewerEngine } from "@/lib/viewer/engine";

export function PlanImportWorkspace() {
  const engineRef = useRef<ViewerEngine | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [scaleNote, setScaleNote] = useState("units mm");
  const [hints, setHints] = useState("page 1");
  const [isLoading, setIsLoading] = useState(false);
  const [hasModel, setHasModel] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [ingestSummary, setIngestSummary] = useState("");
  const [wireframeNote, setWireframeNote] = useState("");
  const [error, setError] = useState("");

  const handleEngineReady = useCallback((engine: ViewerEngine | null) => {
    engineRef.current = engine;
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!pdfFile || isLoading) return;
    setError("");
    setStatusText("");
    setIngestSummary("");
    setWireframeNote("");
    setIsLoading(true);

    let objectUrl: string | undefined;

    try {
      const { blob, specSummary, intentSummary } = await fetchPdfToIfc(pdfFile, {
        scaleNote,
        hints,
      });

      objectUrl = createIfcObjectUrl(blob);
      const engine = engineRef.current;
      if (!engine) {
        throw new Error(he.aiDesignerViewerNotReady);
      }

      await loadIfcBlobIntoViewer(engine, blob, objectUrl);
      objectUrl = undefined;
      setHasModel(true);
      if (intentSummary?.includes("vector_pdf")) {
        setWireframeNote(he.planImportWireframeNote);
      } else if (intentSummary?.includes("vision_llm")) {
        setWireframeNote(he.planImportAccuracyNote);
      }
      setStatusText(
        [specSummary, intentSummary].filter(Boolean).join(" · ") || he.planImportSuccess,
      );
    } catch (err) {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
      if (err instanceof PdfPlanError) {
        setError(
          err.message.includes("OpenAI") ||
            err.message.includes("vision") ||
            err.message.includes("vector strokes") ||
            err.message.includes("Vector extraction")
            ? `${err.message} Tip: Scale = "units mm", Hints = "page 1". Check http://127.0.0.1:8013/health → pdf_dense_cad_primary should be "vector_pdf".`
            : err.message,
        );
      } else if (err instanceof IfcLoadError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(he.planImportError);
      }
    } finally {
      setIsLoading(false);
    }
  }, [hints, isLoading, pdfFile, scaleNote]);

  const handleDownloadJson = useCallback(async () => {
    if (!pdfFile || isLoading) return;
    setError("");
    setIsLoading(true);
    try {
      const result = await fetchPdfToStructuralJson(pdfFile, { scaleNote, hints });
      const blob = new Blob([JSON.stringify(result, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "structural-model.json";
      anchor.click();
      URL.revokeObjectURL(url);
      const members = result.validation?.element_count ?? 0;
      setIngestSummary(
        `Pages ${result.ingest.page_count} · ${result.ingest.text_char_count} text chars · ` +
          `${result.ingest.drawing_op_count} vector ops · method: ${result.extraction_method}`,
      );
      const aiLabel = result.ai_model ? ` · ${result.ai_model}` : "";
      setStatusText(
        `${he.planImportJsonSaved} (${result.status}, ${members} members, ${result.extraction_method}${aiLabel})`,
      );
    } catch (err) {
      setError(err instanceof PdfPlanError ? err.message : he.planImportError);
    } finally {
      setIsLoading(false);
    }
  }, [hints, isLoading, pdfFile, scaleNote]);

  return (
    <div className="flex h-dvh min-h-0 flex-col bg-zinc-950 text-slate-100">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/80 px-4 py-2.5 safe-top">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
        >
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          {he.aiDesignerBackHome}
        </Link>
        <span className="text-xs text-slate-500">{he.planImportTitle}</span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex w-full shrink-0 flex-col gap-4 border-b border-slate-800 bg-slate-900/60 p-4 lg:w-[360px] lg:border-b-0 lg:border-e">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/15 ring-1 ring-amber-400/30">
              <FileUp className="h-5 w-5 text-amber-400" aria-hidden />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-slate-100">{he.planImportTitle}</h1>
              <p className="text-xs text-slate-400">{he.planImportSubtitle}</p>
            </div>
          </div>

          <label className="block text-xs font-medium text-slate-300">{he.planImportFileLabel}</label>
          <input
            type="file"
            accept=".pdf,application/pdf"
            className="w-full rounded-xl border border-dashed border-zinc-600 bg-zinc-950 p-3 text-xs file:me-2 file:rounded-lg file:border-0 file:bg-amber-600 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white"
            onChange={(e) => {
              setError("");
              setPdfFile(e.target.files?.[0] ?? null);
            }}
          />
          <p className="text-xs text-zinc-500">{pdfFile?.name ?? he.planImportNoFile}</p>

          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200/90">
            {he.planImportAccuracyNote}{" "}
            <Link href="/ai-designer" className="underline hover:text-amber-100">
              {he.planImportAccuracyLink}
            </Link>
          </p>

          <label className="block text-xs font-medium text-slate-300">{he.planImportScaleLabel}</label>
          <input
            type="text"
            value={scaleNote}
            onChange={(e) => setScaleNote(e.target.value)}
            placeholder={he.planImportScalePlaceholder}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-slate-100"
          />

          <label className="block text-xs font-medium text-slate-300">{he.planImportHintsLabel}</label>
          <textarea
            value={hints}
            onChange={(e) => setHints(e.target.value)}
            placeholder={he.planImportHintsPlaceholder}
            rows={3}
            className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-slate-100"
          />

          {wireframeNote && (
            <p className="text-xs text-amber-400/90">{wireframeNote}</p>
          )}
          {ingestSummary && <p className="text-xs text-slate-500">{ingestSummary}</p>}
          {error && <p className="text-xs text-red-400">{error}</p>}
          {statusText && !error && <p className="text-xs text-emerald-400">{statusText}</p>}

          <Button
            size="lg"
            className="w-full"
            disabled={!pdfFile || isLoading}
            onClick={() => void handleGenerate()}
          >
            {isLoading ? he.planImportGenerating : he.planImportGenerate}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={!pdfFile || isLoading}
            onClick={() => void handleDownloadJson()}
          >
            {he.planImportDownloadJson}
          </Button>
          <Link
            href="/plan-crop"
            className="block w-full rounded-lg border border-[#00ffcc]/40 px-3 py-2 text-center text-xs text-[#00ffcc] transition hover:bg-[#00ffcc]/10"
          >
            {he.planImportCropLink}
          </Link>
        </aside>

        <section className="relative min-h-0 flex-1">
          <AiDesignerViewport
            hasModel={hasModel}
            onEngineReady={handleEngineReady}
            placeholderMessage={he.planImportViewportWaiting}
            className="h-full min-h-[50vh] lg:min-h-0"
          />
          <AiLoadingOverlay visible={isLoading} />
        </section>
      </div>
    </div>
  );
}
