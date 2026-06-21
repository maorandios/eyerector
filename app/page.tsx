"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { he } from "@/lib/i18n/he";
import { useAppStore } from "@/lib/state/app-store";

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
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col justify-center gap-4 p-4 safe-bottom safe-top">
      <Card className="space-y-5 rounded-[1.75rem] border-zinc-700/80 bg-zinc-900/90 p-5 shadow-2xl">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-black tracking-tight">{he.appName}</h1>
          <h2 className="text-xl font-bold">{he.uploadTitle}</h2>
          <p className="text-sm leading-6 text-zinc-400">{he.uploadSubtitle}</p>
        </div>
        <label
          className="relative flex min-h-40 w-full cursor-pointer flex-col items-center justify-center gap-3 overflow-hidden rounded-[1.5rem] border border-dashed border-zinc-600 bg-zinc-950/80 p-5 text-center transition active:scale-[0.99]"
        >
          <input
            type="file"
            accept=".ifc,.ifczip,.ifcxml,application/octet-stream,*/*"
            className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0"
            onClick={(e) => {
              e.currentTarget.value = "";
            }}
            onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
          />
          <span className="flex size-14 items-center justify-center rounded-2xl bg-blue-500/15 text-blue-300 ring-1 ring-blue-400/30">
            <FileUp className="size-7" aria-hidden />
          </span>
          <span className="text-base font-bold text-zinc-100">
            {fileName ? "החלף קובץ IFC" : "בחר קובץ IFC"}
          </span>
          <span className="max-w-xs text-xs leading-5 text-zinc-500">
            עובד גם ממנהל הקבצים בטלפון. אחרי הבחירה לחץ על פתיחת מודל.
          </span>
        </label>
        <p className="truncate text-center text-sm font-medium text-zinc-300" dir="ltr">
          {fileName || "לא נבחר קובץ"}
        </p>
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
          className="h-14 w-full rounded-2xl text-base font-bold"
          disabled={!fileName || analyzing}
          onClick={openModel}
        >
          {analyzing ? "מנתח מודל..." : he.openModel}
        </Button>
      </Card>
    </main>
  );
}
