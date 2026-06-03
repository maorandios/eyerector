"use client";

import { useCallback, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { he } from "@/lib/i18n/he";
import type { RegionAnalyzeDebug } from "@/lib/plan-crop/types";
import { cn } from "@/lib/utils";

type DebugTab = "vision_raw" | "after_enrich" | "full_response";

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

type RegionAnalyzeDebugPanelProps = {
  debug: RegionAnalyzeDebug;
};

export function RegionAnalyzeDebugPanel({ debug }: RegionAnalyzeDebugPanelProps) {
  const [open, setOpen] = useState(true);
  const [tab, setTab] = useState<DebugTab>("vision_raw");
  const [copied, setCopied] = useState(false);

  const payload = useMemo(() => {
    switch (tab) {
      case "vision_raw":
        return debug.vision_raw;
      case "after_enrich":
        return debug.analysis_after_enrich;
      case "full_response":
        return debug.full_api_response;
      default:
        return debug.vision_raw;
    }
  }, [tab, debug]);

  const text = useMemo(() => formatJson(payload), [payload]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, [text]);

  const tabs: { id: DebugTab; label: string }[] = [
    { id: "vision_raw", label: he.planCropDebugTabGptRaw },
    { id: "after_enrich", label: he.planCropDebugTabEnriched },
    { id: "full_response", label: he.planCropDebugTabFull },
  ];

  return (
    <div className="rounded-lg border border-amber-800/60 bg-amber-950/20">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-start text-sm font-medium text-amber-200/90"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
        {he.planCropDebugTitle}
        {debug.ai_model ? (
          <span className="ms-auto text-xs font-normal text-slate-500">{debug.ai_model}</span>
        ) : null}
      </button>
      {open ? (
        <div className="border-t border-amber-800/40 px-3 pb-3 pt-2">
          <p className="mb-2 text-xs text-slate-500">{he.planCropDebugHint}</p>
          <div className="mb-2 flex flex-wrap gap-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                className={cn(
                  "rounded px-2 py-1 text-xs",
                  tab === t.id
                    ? "bg-amber-900/50 text-amber-100"
                    : "text-slate-400 hover:bg-slate-800",
                )}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="ms-auto h-7 gap-1 px-2 text-xs text-slate-400"
              onClick={() => void handleCopy()}
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? he.planCropDebugCopied : he.planCropDebugCopy}
            </Button>
          </div>
          <pre className="max-h-[40vh] overflow-auto rounded border border-slate-700 bg-slate-950 p-2 font-mono text-[11px] leading-relaxed text-emerald-200/90">
            {text}
          </pre>
          <p className="mt-1 text-[10px] text-slate-600">
            {he.planCropDebugFetched}: {debug.fetchedAt}
          </p>
        </div>
      ) : null}
    </div>
  );
}
