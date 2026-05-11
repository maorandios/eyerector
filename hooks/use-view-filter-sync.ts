"use client";

import { useEffect, useRef } from "react";
import type { AnalyzerOutput } from "@/types/domain";
import type { ViewerEngine } from "@/lib/viewer/engine";
import { useViewFilterStore } from "@/lib/state/view-filter-store";
import { useIsolationStore } from "@/lib/state/isolation-store";
import {
  resolveGhostRevealLocals,
  resolveViewFilterHiddenLocals,
} from "@/lib/viewer/view-filter-resolve";

/**
 * Pushes {@link useViewFilterStore} onto the fragments worker (`applyViewVisibilityFilter`).
 * Clears isolation visuals + highlight first so visibility state stays consistent.
 */
export function useViewFilterSync(
  engine: ViewerEngine | null,
  analyzerData: AnalyzerOutput | null,
  loadingState: "idle" | "loading" | "parsing" | "ready" | "error",
) {
  const assemblySig = useViewFilterStore((s) =>
    Object.keys(s.hiddenAssemblyKeys)
      .sort()
      .join("\0"),
  );
  const partSig = useViewFilterStore((s) =>
    Object.keys(s.hiddenPartIds)
      .sort()
      .join("\0"),
  );
  const partTabSig = useViewFilterStore((s) =>
    Object.keys(s.hiddenPartTabGroupKeys)
      .sort()
      .join("\0"),
  );
  const profileTabSig = useViewFilterStore((s) =>
    Object.keys(s.hiddenProfileTabGroupKeys)
      .sort()
      .join("\0"),
  );
  const hideAllFastenersKeepHoles = useViewFilterStore((s) => s.hideAllFastenersKeepHoles);
  const ghostFocusTab = useViewFilterStore((s) => s.ghostFocusTab);
  const ghostRevealSig = useViewFilterStore((s) =>
    Object.keys(s.ghostRevealedPartIds)
      .sort()
      .join("\0"),
  );

  const gen = useRef(0);

  useEffect(() => {
    if (!engine || loadingState !== "ready" || !analyzerData) return;

    const run = async () => {
      const my = ++gen.current;
      const filter = useViewFilterStore.getState();

      if (filter.ghostFocusTab) {
        await engine.clearIsolationVisuals();
        if (my !== gen.current) return;
        useIsolationStore.getState().clearIsolation();
        await engine.clearHighlight();
        if (my !== gen.current) return;
        const { structuralHidden, fastenerHidden } = await resolveViewFilterHiddenLocals(engine, analyzerData, {
          hiddenAssemblyKeys: filter.hiddenAssemblyKeys,
          hiddenPartIds: filter.hiddenPartIds,
          hiddenPartTabGroupKeys: filter.hiddenPartTabGroupKeys,
          hiddenProfileTabGroupKeys: filter.hiddenProfileTabGroupKeys,
          hideAllFastenersKeepHoles: filter.hideAllFastenersKeepHoles,
        });
        if (my !== gen.current) return;
        await engine.applyViewVisibilityFilter(structuralHidden, fastenerHidden);
        if (my !== gen.current) return;
        const revealedLocals = await resolveGhostRevealLocals(engine, analyzerData, filter.ghostRevealedPartIds);
        if (my !== gen.current) return;
        await engine.applyIsolation("context", new Set(revealedLocals), {
          focus: revealedLocals.length > 0,
        });
        return;
      }

      await engine.clearIsolationVisuals();
      if (my !== gen.current) return;
      useIsolationStore.getState().clearIsolation();
      await engine.clearHighlight();
      if (my !== gen.current) return;
      const nextFilter = useViewFilterStore.getState();
      const { structuralHidden, fastenerHidden } = await resolveViewFilterHiddenLocals(engine, analyzerData, {
        hiddenAssemblyKeys: nextFilter.hiddenAssemblyKeys,
        hiddenPartIds: nextFilter.hiddenPartIds,
        hiddenPartTabGroupKeys: nextFilter.hiddenPartTabGroupKeys,
        hiddenProfileTabGroupKeys: nextFilter.hiddenProfileTabGroupKeys,
        hideAllFastenersKeepHoles: nextFilter.hideAllFastenersKeepHoles,
      });
      if (my !== gen.current) return;
      await engine.applyViewVisibilityFilter(structuralHidden, fastenerHidden);
    };

    void run();
    return () => {
      gen.current++;
    };
  }, [
    engine,
    loadingState,
    analyzerData,
    assemblySig,
    partSig,
    partTabSig,
    profileTabSig,
    hideAllFastenersKeepHoles,
    ghostFocusTab,
    ghostRevealSig,
  ]);
}
