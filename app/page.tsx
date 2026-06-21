"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { saveIfcFileForViewer } from "@/lib/browser-ifc-file-store";
import { he } from "@/lib/i18n/he";
import { useAppStore } from "@/lib/state/app-store";

export default function HomePage() {
  const router = useRouter();
  const primaryFileInputRef = useRef<HTMLInputElement | null>(null);
  const fallbackFileInputRef = useRef<HTMLInputElement | null>(null);
  const lastFileSigRef = useRef("");
  const [error, setError] = useState("");
  const [opening, setOpening] = useState(false);
  const { setFile, file, fileName, loadingState, setLoadingState, setAnalyzerData } = useAppStore();

  const persistFileForRecovery = (selectedFile: File) => {
    void saveIfcFileForViewer(selectedFile).catch((err) => {
      console.warn("Could not persist IFC file for viewer recovery:", err);
    });
  };

  const openSelectedFile = (selectedFile: File) => {
    setFile(selectedFile);
    setAnalyzerData(null);
    setLoadingState("loading");
    setOpening(true);
    persistFileForRecovery(selectedFile);
    router.push("/viewer");
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
    openSelectedFile(selectedFile);
  };

  const selectedFileFromInputs = () =>
    primaryFileInputRef.current?.files?.[0] ??
    fallbackFileInputRef.current?.files?.[0] ??
    file;

  const handleFileInput = (input: HTMLInputElement) => {
    onFileChange(input.files?.[0] ?? null);
  };

  const openModel = () => {
    const selectedFile = selectedFileFromInputs();
    if (!selectedFile) {
      setError("בחר קובץ IFC ואז לחץ פתיחת מודל.");
      return;
    }
    openSelectedFile(selectedFile);
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col justify-center gap-4 p-4 safe-bottom safe-top">
      <Card className="space-y-5 rounded-[1.75rem] border-zinc-700/80 bg-zinc-900/90 p-5 shadow-2xl">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-black tracking-tight">{he.appName}</h1>
          <h2 className="text-xl font-bold">{he.uploadTitle}</h2>
          <p className="text-sm leading-6 text-zinc-400">{he.uploadSubtitle}</p>
        </div>
        <label className="relative block overflow-hidden rounded-[1.5rem] border border-dashed border-zinc-600 bg-zinc-950/80 p-5 text-center active:border-blue-400 active:bg-blue-950/30">
          <input
            ref={primaryFileInputRef}
            type="file"
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
            onInput={(e) => handleFileInput(e.currentTarget)}
            onChange={(e) => handleFileInput(e.currentTarget)}
          />
          <span className="block text-lg font-black text-zinc-100">
            {fileName ? "החלף קובץ IFC" : "בחר קובץ IFC"}
          </span>
          <span className="mt-2 block text-sm leading-6 text-zinc-400">
            הקש כאן ובחר קובץ מהטלפון. המודל ייפתח מיד אחרי הבחירה.
          </span>
        </label>
        <div className="rounded-2xl border border-zinc-700 bg-zinc-950 p-3">
          <p className="mb-2 text-center text-xs font-semibold text-zinc-400">
            אם הבחירה למעלה לא מגיבה באייפון, השתמש בשדה המקורי כאן:
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
              ? opening
                ? "פותח מודל..."
                : he.loading
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
          onClick={openModel}
        >
          {he.openModel}
        </Button>
      </Card>
    </main>
  );
}
