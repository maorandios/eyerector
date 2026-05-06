"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { he } from "@/lib/i18n/he";
import { useAppStore } from "@/lib/state/app-store";

export default function HomePage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const { setFile, fileName, loadingState, setLoadingState } = useAppStore();

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

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-xl flex-col justify-center p-4">
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
          disabled={!fileName}
          onClick={() => router.push("/viewer")}
        >
          {he.openModel}
        </Button>
      </Card>
    </main>
  );
}
