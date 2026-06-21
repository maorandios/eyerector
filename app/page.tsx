"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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
  const primaryFileInputRef = useRef<HTMLInputElement | null>(null);
  const fallbackFileInputRef = useRef<HTMLInputElement | null>(null);
  const lastFileSigRef = useRef("");
  const [error, setError] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [pendingViewerOpen, setPendingViewerOpen] = useState(false);
  const { setFile, file, fileName, loadingState, setLoadingState, setAnalyzerData } = useAppStore();

  useEffect(() => {
    if (!pendingViewerOpen || !file) return;
    router.push("/viewer");
  }, [file, pendingViewerOpen, router]);

  const analyzeFileInBackground = async (selectedFile: File) => {
    setAnalyzing(true);
    try {
      const formData = new FormData();
      const fileNameForUpload = selectedFile.name.trim().toLowerCase().endsWith(".ifc")
        ? selectedFile.name
        : `${selectedFile.name.trim() || "model"}.ifc`;
      formData.append("file", selectedFile, fileNameForUpload);
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
    } catch (err) {
      console.error("Analyzer failed:", err);
      setError("המודל נפתח, אבל ניתוח הנתונים נכשל. נסה קובץ IFC אחר אם רשימות החיפוש ריקות.");
    } finally {
      setAnalyzing(false);
    }
  };

  const onFileChange = (selectedFile: File | null) => {
    setError("");
    if (!selectedFile) {
      setFile(null);
      lastFileSigRef.current = "";
      return;
    }
    const sig = `${selectedFile.name}:${selectedFile.size}:${selectedFile.lastModified}`;
    if (sig === lastFileSigRef.current) return;
    lastFileSigRef.current = sig;
    if (selectedFile.size === 0) {
      setLoadingState("error");
      setError("הקובץ שנבחר ריק. בחר קובץ IFC אחר.");
      return;
    }
    setFile(selectedFile);
    setAnalyzerData(null);
    setLoadingState("loading");
    setPendingViewerOpen(true);
    void analyzeFileInBackground(selectedFile);
  };

  const selectedFileFromInputs = () =>
    primaryFileInputRef.current?.files?.[0] ??
    fallbackFileInputRef.current?.files?.[0] ??
    file;

  const handleFileInput = (input: HTMLInputElement) => {
    onFileChange(input.files?.[0] ?? null);
  };

  const openModel = async () => {
    const selectedFile = selectedFileFromInputs();
    if (!selectedFile || analyzing) {
      setError("בחר קובץ IFC ואז לחץ פתיחת מודל.");
      return;
    }
    setFile(selectedFile);
    setAnalyzerData(null);
    setLoadingState("loading");
    router.push("/viewer");
    void analyzeFileInBackground(selectedFile);
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col justify-center gap-4 p-4 safe-bottom safe-top">
      <Card className="space-y-5 rounded-[1.75rem] border-zinc-700/80 bg-zinc-900/90 p-5 shadow-2xl">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-black tracking-tight">{he.appName}</h1>
          <h2 className="text-xl font-bold">{he.uploadTitle}</h2>
          <p className="text-sm leading-6 text-zinc-400">{he.uploadSubtitle}</p>
        </div>
        <div className="space-y-3 rounded-[1.5rem] border border-dashed border-zinc-600 bg-zinc-950/80 p-4">
          <p className="text-center text-base font-bold text-zinc-100">
            {fileName ? "החלף קובץ IFC" : "בחר קובץ IFC"}
          </p>
          <input
            ref={primaryFileInputRef}
            type="file"
            className="block w-full rounded-2xl border border-zinc-700 bg-zinc-900 p-4 text-base text-zinc-100"
            onInput={(e) => handleFileInput(e.currentTarget)}
            onChange={(e) => handleFileInput(e.currentTarget)}
          />
          <p className="text-center text-xs leading-5 text-zinc-500">
            עובד גם ממנהל הקבצים בטלפון. אחרי הבחירה המודל ייטען אוטומטית.
          </p>
        </div>
        <div className="rounded-2xl border border-zinc-700 bg-zinc-950 p-3">
          <p className="mb-2 text-center text-xs font-semibold text-zinc-400">
            אם הכפתור למעלה לא מגיב באייפון, השתמש בשדה המקורי כאן:
          </p>
          <input
            ref={fallbackFileInputRef}
            type="file"
            className="block w-full text-base text-zinc-100"
            onInput={(e) => handleFileInput(e.currentTarget)}
            onChange={(e) => handleFileInput(e.currentTarget)}
          />
        </div>
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
          disabled={analyzing}
          onClick={openModel}
        >
          {analyzing ? "מנתח מודל..." : he.openModel}
        </Button>
      </Card>
    </main>
  );
}
