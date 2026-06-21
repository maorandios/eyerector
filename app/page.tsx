"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
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
  const [nativeFileStatus, setNativeFileStatus] = useState("");
  const [debugStatus, setDebugStatus] = useState("JS starting");
  const [heartbeat, setHeartbeat] = useState(0);
  const { setFile, file, fileName, loadingState, setLoadingState, setAnalyzerData } = useAppStore();

  const forceOpenViewer = useCallback(() => {
    router.push("/viewer");
    window.setTimeout(() => {
      if (window.location.pathname !== "/viewer") {
        window.location.assign("/viewer");
      }
    }, 900);
  }, [router]);

  const persistFileForRecovery = useCallback(async (selectedFile: File) => {
    await saveIfcFileForViewer(selectedFile);
  }, []);

  const openSelectedFile = useCallback((selectedFile: File) => {
    setFile(selectedFile);
    setAnalyzerData(null);
    setLoadingState("loading");
    setOpening(true);
    setDebugStatus(`Opening ${selectedFile.name || "IFC"} (${selectedFile.size} bytes)`);
    void persistFileForRecovery(selectedFile)
      .then(() => {
        setDebugStatus("IFC saved. Opening viewer...");
        forceOpenViewer();
      })
      .catch((err) => {
        console.warn("Could not persist IFC file for viewer recovery:", err);
        setDebugStatus("IFC save failed. Opening viewer from memory...");
        forceOpenViewer();
      });
  }, [forceOpenViewer, persistFileForRecovery, setAnalyzerData, setFile, setLoadingState]);

  const onFileChange = useCallback((selectedFile: File | null) => {
    setError("");
    if (!selectedFile) {
      setFile(null);
      lastFileSigRef.current = "";
      setNativeFileStatus("");
      setDebugStatus("No native file selected");
      return;
    }
    const displayName = selectedFile.name || "IFC";
    setNativeFileStatus(`${displayName} (${selectedFile.size.toLocaleString()} bytes)`);
    setDebugStatus(`Detected ${displayName} size=${selectedFile.size}`);
    if (selectedFile.size === 0) {
      setLoadingState("loading");
      setError("הקובץ מופיע בטלפון אבל עדיין לא זמין לקריאה. המתן רגע או הורד אותו מקבצי iCloud ואז לחץ פתח מודל.");
      return;
    }
    const sig = `${selectedFile.name}:${selectedFile.size}:${selectedFile.lastModified}`;
    if (sig === lastFileSigRef.current) return;
    lastFileSigRef.current = sig;
    openSelectedFile(selectedFile);
  }, [openSelectedFile, setFile, setLoadingState]);

  const selectedFileFromNativeInputs = useCallback(() => {
    try {
      const selectedFiles = [
        primaryFileInputRef.current?.files?.[0] ?? null,
        fallbackFileInputRef.current?.files?.[0] ?? null,
      ].filter((selectedFile): selectedFile is File => Boolean(selectedFile));
      return selectedFiles.find((selectedFile) => selectedFile.size > 0) ?? selectedFiles[0] ?? null;
    } catch (err) {
      setDebugStatus(`Native file read failed: ${err instanceof Error ? err.message : String(err)}`);
      return null;
    }
  }, []);

  const selectedFileForOpen = () => selectedFileFromNativeInputs() ?? file;

  const handleFileInput = (input: HTMLInputElement) => {
    onFileChange(input.files?.[0] ?? null);
  };

  useEffect(() => {
    if (opening) return;
    const pollNativeFileInputs = window.setInterval(() => {
      const selectedFile = selectedFileFromNativeInputs();
      if (selectedFile) onFileChange(selectedFile);
    }, 300);
    return () => window.clearInterval(pollNativeFileInputs);
  }, [onFileChange, opening, selectedFileFromNativeInputs]);

  useEffect(() => {
    const timer = window.setInterval(() => setHeartbeat((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const openModel = () => {
    const selectedFile = selectedFileForOpen();
    if (!selectedFile) {
      setError("בחר קובץ IFC ואז לחץ פתיחת מודל.");
      return;
    }
    onFileChange(selectedFile);
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col justify-center gap-4 p-4 safe-bottom safe-top">
      <Card className="space-y-5 rounded-[1.75rem] border-zinc-700/80 bg-zinc-900/90 p-5 shadow-2xl">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-black tracking-tight">{he.appName}</h1>
          <h2 className="text-xl font-bold">{he.uploadTitle}</h2>
          <p className="text-sm leading-6 text-zinc-400">{he.uploadSubtitle}</p>
        </div>
        <div className="space-y-3 rounded-[1.5rem] border border-dashed border-zinc-600 bg-zinc-950/80 p-4 text-center">
          <p className="text-base font-bold text-zinc-100">
            {fileName ? "החלף קובץ IFC" : "בחר קובץ IFC"}
          </p>
          <input
            ref={primaryFileInputRef}
            type="file"
            className="block w-full rounded-2xl border border-zinc-700 bg-zinc-900 p-4 text-base text-zinc-100"
            onInput={(e) => handleFileInput(e.currentTarget)}
            onChange={(e) => handleFileInput(e.currentTarget)}
          />
          <p className="text-xs leading-5 text-zinc-500">
            אחרי שהשם מופיע, המודל ייפתח אוטומטית. אם לא, לחץ פתח מודל.
          </p>
        </div>
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
        {nativeFileStatus && (
          <p className="truncate text-center text-xs text-zinc-500" dir="ltr">
            Native picker: {nativeFileStatus}
          </p>
        )}
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-left text-xs text-amber-100" dir="ltr">
          <p>JS heartbeat: {heartbeat}</p>
          <p className="truncate">Status: {debugStatus}</p>
        </div>
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
