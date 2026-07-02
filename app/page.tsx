"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { readAndSaveIfcFile } from "@/lib/browser-ifc-file-store";
import { he } from "@/lib/i18n/he";
import { useAppStore } from "@/lib/state/app-store";

export default function HomePage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const busyRef = useRef(false);
  const lastFailedSigRef = useRef("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("מוכן לבחירת קובץ");
  const [busy, setBusy] = useState(false);
  const { setFile, fileName, setLoadingState, setAnalyzerData } = useAppStore();

  const openViewer = useCallback(() => {
    setStatus("פותח צופה...");
    window.location.assign("/viewer");
  }, []);

  const processSelectedFile = useCallback(async (selectedFile: File | null) => {
    if (!selectedFile || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    setStatus(`נבחר: ${selectedFile.name || "IFC"}`);

    try {
      const readyFile = await readAndSaveIfcFile(selectedFile, setStatus);
      lastFailedSigRef.current = "";
      setFile(readyFile);
      setAnalyzerData(null);
      setLoadingState("loading");
      setStatus(`נשמר (${readyFile.size.toLocaleString()} bytes). פותח צופה...`);
      openViewer();
    } catch (err) {
      const sig = `${selectedFile.name}:${selectedFile.size}:${selectedFile.lastModified}`;
      lastFailedSigRef.current = selectedFile.size > 0 ? sig : "";
      const message =
        err instanceof Error
          ? err.message
          : "לא ניתן לקרוא את הקובץ מהטלפון. הורד אותו מ-iCloud/קבצים ונסה שוב.";
      setError(message);
      setStatus("שגיאה בקריאת הקובץ");
      busyRef.current = false;
      setBusy(false);
    }
  }, [openViewer, setAnalyzerData, setFile, setLoadingState]);

  const onInputChange = (input: HTMLInputElement) => {
    void processSelectedFile(input.files?.[0] ?? null);
  };

  const openModel = () => {
    const selectedFile = fileInputRef.current?.files?.[0] ?? null;
    if (!selectedFile) {
      setError("בחר קובץ IFC מהטלפון ואז לחץ פתח מודל.");
      return;
    }
    void processSelectedFile(selectedFile);
  };

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (busyRef.current) return;
      const selectedFile = fileInputRef.current?.files?.[0] ?? null;
      if (!selectedFile) return;
      const sig = `${selectedFile.name}:${selectedFile.size}:${selectedFile.lastModified}`;
      if (selectedFile.size === 0 || sig !== lastFailedSigRef.current) {
        void processSelectedFile(selectedFile);
      }
    }, 400);
    return () => window.clearInterval(timer);
  }, [processSelectedFile]);

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
            ref={fileInputRef}
            type="file"
            accept=".ifc,.IFC,application/octet-stream"
            className="block w-full rounded-2xl border border-zinc-700 bg-zinc-900 p-4 text-base text-zinc-100"
            disabled={busy}
            onInput={(e) => onInputChange(e.currentTarget)}
            onChange={(e) => onInputChange(e.currentTarget)}
          />
          <p className="text-xs leading-5 text-zinc-500">
            אם הקובץ ב-iCloud, המתן עד שההורדה מסתיימת. אחרי הבחירה המודל ייפתח אוטומטית.
          </p>
        </div>

        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-center text-sm text-amber-100">
          {status}
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <Button
          size="lg"
          className="h-14 w-full rounded-2xl text-base font-bold"
          disabled={busy}
          onClick={openModel}
        >
          {busy ? "קורא קובץ..." : he.openModel}
        </Button>
      </Card>
    </main>
  );
}
