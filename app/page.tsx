"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { FileUp, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { he } from "@/lib/i18n/he";
import { useAppStore } from "@/lib/state/app-store";
import { cn } from "@/lib/utils";

const RAW_ANALYZER_API_URL = process.env.NEXT_PUBLIC_ANALYZER_API_URL?.trim();
const ANALYZER_API_URL = RAW_ANALYZER_API_URL
  ? (RAW_ANALYZER_API_URL.match(/^https?:\/\//i)
      ? RAW_ANALYZER_API_URL
      : `https://${RAW_ANALYZER_API_URL}`
    ).replace(/\/$/, "")
  : "";

export default function HomePage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const { setFile, file, fileName, loadingState, setLoadingState, setAnalyzerData } = useAppStore();

  const onFileChange = (file: File | null) => {
    setError("");
    if (!file) {
      setFile(null);
      return;
    }
    if (!file.name.toLowerCase().endsWith(".ifc")) {
      setError("ניתן לבחור רק קובץ IFC");
      return;
    }
    setFile(file);
    setLoadingState("ready");
  };

  const openModel = async () => {
    if (!file) return;
    setError("");
    setAnalyzing(true);
    setLoadingState("parsing");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const analyzerEndpoint = ANALYZER_API_URL
        ? `${ANALYZER_API_URL}/analyze-ifc`
        : "/api/analyze-ifc";
      const response = await fetch(analyzerEndpoint, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || payload.error || "Analyzer request failed");
      }
      const analyzerData = await response.json();
      setAnalyzerData(analyzerData);
      setLoadingState("ready");
      router.push("/viewer");
    } catch (err) {
      console.error("Analyzer failed:", err);
      setLoadingState("error");
      setError("ניתוח IFC נכשל. בדוק ש-Python ו-IfcOpenShell מותקנים.");
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-xl flex-col justify-center gap-4 p-4">
      <Link
        href="/ai-designer"
        className={cn(
          "group relative overflow-hidden rounded-2xl border border-cyan-500/30 p-4",
          "bg-gradient-to-br from-cyan-950/80 via-slate-900 to-emerald-950/60",
          "shadow-lg shadow-cyan-950/30 transition hover:border-cyan-400/50 hover:shadow-cyan-900/40",
        )}
      >
        <div className="pointer-events-none absolute -end-8 -top-8 h-32 w-32 rounded-full bg-cyan-500/10 blur-2xl transition group-hover:bg-cyan-500/20" />
        <div className="relative flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-cyan-500/15 ring-1 ring-cyan-400/30">
            <Sparkles className="h-6 w-6 text-cyan-400" aria-hidden />
          </div>
          <div className="min-w-0 flex-1 text-start">
            <p className="text-base font-semibold text-slate-100">{he.createWithAi}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-400">
              {he.createWithAiSubtitle}
            </p>
          </div>
        </div>
      </Link>

      <Link
        href="/plan-crop"
        className={cn(
          "group relative overflow-hidden rounded-2xl border border-[#00ffcc]/30 p-4",
          "bg-gradient-to-br from-teal-950/80 via-slate-900 to-cyan-950/50",
          "shadow-lg shadow-teal-950/20 transition hover:border-[#00ffcc]/50",
        )}
      >
        <div className="pointer-events-none absolute -end-8 -top-8 h-32 w-32 rounded-full bg-[#00ffcc]/10 blur-2xl" />
        <div className="relative flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[#00ffcc]/15 ring-1 ring-[#00ffcc]/30">
            <FileUp className="h-6 w-6 text-[#00ffcc]" aria-hidden />
          </div>
          <div className="min-w-0 flex-1 text-start">
            <p className="text-base font-semibold text-slate-100">{he.planCropFromHomeTitle}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-400">
              {he.planCropFromHomeSubtitle}
            </p>
          </div>
        </div>
      </Link>

      <Link
        href="/plan-import"
        className={cn(
          "group relative overflow-hidden rounded-2xl border border-amber-500/30 p-4",
          "bg-gradient-to-br from-amber-950/80 via-slate-900 to-orange-950/50",
          "shadow-lg shadow-amber-950/20 transition hover:border-amber-400/50 hover:shadow-amber-900/30",
        )}
      >
        <div className="pointer-events-none absolute -end-8 -top-8 h-32 w-32 rounded-full bg-amber-500/10 blur-2xl transition group-hover:bg-amber-500/20" />
        <div className="relative flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 ring-1 ring-amber-400/30">
            <FileUp className="h-6 w-6 text-amber-400" aria-hidden />
          </div>
          <div className="min-w-0 flex-1 text-start">
            <p className="text-base font-semibold text-slate-100">{he.planImportFromHomeTitle}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-400">
              {he.planImportFromHomeSubtitle}
            </p>
          </div>
        </div>
      </Link>

      <Card className="space-y-4">
        <h1 className="text-2xl font-bold">{he.appName}</h1>
        <h2 className="text-lg font-semibold">{he.uploadTitle}</h2>
        <p className="text-sm text-zinc-400">{he.uploadSubtitle}</p>
        <input
          type="file"
          accept=".ifc"
          className="w-full rounded-xl border border-dashed border-zinc-600 bg-zinc-950 p-4 text-sm"
          onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
        />
        <p className="text-sm text-zinc-300">{fileName || "לא נבחר קובץ"}</p>
        {loadingState !== "idle" && (
          <p className="text-xs text-zinc-400">
            {loadingState === "loading"
              ? he.loading
              : loadingState === "parsing"
                ? he.parsing
                : loadingState === "ready"
                  ? he.ready
                  : "שגיאה"}
          </p>
        )}
        {error && <p className="text-sm text-red-400">{error}</p>}
        <Button
          size="lg"
          className="w-full"
          disabled={!fileName || analyzing}
          onClick={openModel}
        >
          {analyzing ? "מנתח מודל..." : he.openModel}
        </Button>
      </Card>
    </main>
  );
}
