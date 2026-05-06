"use client";

import type { Assembly } from "@/types/domain";
import { Card } from "@/components/ui/card";

export function ProductionPanel({ assembly }: { assembly: Assembly | null }) {
  if (!assembly) return <p className="text-sm text-zinc-400">בחר Assembly להצגה</p>;
  return (
    <div className="space-y-2">
      <Card>
        <p className="text-lg font-bold">{assembly.mark || "ללא סימון"}</p>
        <p className="text-xs text-zinc-400">כמות חלקים: {assembly.partCount}</p>
      </Card>
      {assembly.parts.slice(0, 8).map((part) => (
        <Card key={part.expressId} className="space-y-1">
          <p className="text-sm font-semibold">{part.mark || "ללא סימון חלק"}</p>
          <p className="text-xs text-zinc-400">{part.type}</p>
          <p className="text-xs text-zinc-400">{part.profile || "-"}</p>
          <p className="text-xs text-zinc-400">{part.material || "-"}</p>
        </Card>
      ))}
    </div>
  );
}
