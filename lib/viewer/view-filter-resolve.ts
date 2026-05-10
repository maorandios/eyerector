import type { AnalyzerPart, AnalyzerOutput } from "@/types/domain";
import { isAnalyzerBoltRow } from "@/types/domain";
import { analyzerRefsFromAssembly } from "@/lib/viewer/ifc-guid";
import { aggregateAssembliesByMark } from "@/lib/viewer/modelAggregates";
import type { ViewerEngine } from "@/lib/viewer/engine";
import {
  aggregateProfilesForModelTab,
  aggregateSteelPartsForModelTab,
} from "@/components/viewer/SelectionPickDetails";

type FilterPick = {
  hiddenAssemblyKeys: Record<string, boolean>;
  hiddenPartIds: Record<string, boolean>;
  hiddenPartTabGroupKeys: Record<string, boolean>;
  hiddenProfileTabGroupKeys: Record<string, boolean>;
};

/**
 * Resolves analyzer + filter picks to fragment local ids for `setVisible(..., false)`.
 * Union of assembly-group hides and per-part hides (overlapping ids are fine).
 */
export async function resolveViewFilterHiddenLocals(
  engine: ViewerEngine,
  analyzerData: AnalyzerOutput,
  filter: FilterPick,
): Promise<Set<number>> {
  const out = new Set<number>();
  const asmKeys = Object.keys(filter.hiddenAssemblyKeys);
  const partIds = Object.keys(filter.hiddenPartIds);
  const partTabKeys = Object.keys(filter.hiddenPartTabGroupKeys);
  const profileTabKeys = Object.keys(filter.hiddenProfileTabGroupKeys);

  const steelParts = analyzerData.parts.filter((p): p is AnalyzerPart => !isAnalyzerBoltRow(p));

  if (asmKeys.length > 0) {
    const rows = aggregateAssembliesByMark(analyzerData.assemblies);
    const byKey = new Map(rows.map((r) => [r.key, r] as const));
    for (const k of asmKeys) {
      const row = byKey.get(k);
      if (!row) continue;
      for (const inst of row.instances) {
        const refs = analyzerRefsFromAssembly(inst);
        const set = await engine.resolveIsolationLocalIds(refs);
        set.forEach((id) => out.add(id));
      }
    }
  }

  const pushPartLocals = async (parts: AnalyzerPart[]) => {
    for (const p of parts) {
      const set = await engine.resolveIsolationLocalIds([{ id: p.id, expressId: p.expressId }]);
      set.forEach((id) => out.add(id));
    }
  };

  if (partIds.length > 0) {
    for (const pid of partIds) {
      const part = analyzerData.parts.find((p) => p.id === pid);
      if (!part || isAnalyzerBoltRow(part)) continue;
      await pushPartLocals([part]);
    }
  }

  if (partTabKeys.length > 0) {
    const rows = aggregateSteelPartsForModelTab(steelParts);
    const byKey = new Map(rows.map((r) => [r.key, r] as const));
    for (const k of partTabKeys) {
      const row = byKey.get(k);
      if (!row) continue;
      await pushPartLocals(row.instances);
    }
  }

  if (profileTabKeys.length > 0) {
    const rows = aggregateProfilesForModelTab(steelParts);
    const byKey = new Map(rows.map((r) => [r.key, r] as const));
    for (const k of profileTabKeys) {
      const row = byKey.get(k);
      if (!row) continue;
      await pushPartLocals(row.instances);
    }
  }

  return out;
}
