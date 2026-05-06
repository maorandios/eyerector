"use client";

import { Card } from "@/components/ui/card";
import type { Element } from "@/types/domain";

export function ManagementPanel({ element }: { element: Element | null }) {
  if (!element) return <p className="text-sm text-zinc-400">לא נבחר אלמנט</p>;
  return (
    <Card className="space-y-1">
      <p className="text-sm font-semibold">{element.name || "ללא שם"}</p>
      <p className="text-xs text-zinc-400">סוג IFC: {element.ifcType}</p>
      <p className="text-xs text-zinc-400">Assembly mark: {element.assemblyMark || "-"}</p>
      <p className="text-xs text-zinc-400">Part mark: {element.partMark || "-"}</p>
      <p className="text-xs text-zinc-400">Profile: {element.profile || "-"}</p>
      <p className="text-xs text-zinc-400">Material: {element.material || "-"}</p>
      <details className="mt-2 text-xs text-zinc-500">
        <summary>מתקדם / Debug</summary>
        Express ID: {element.expressId}
      </details>
    </Card>
  );
}
