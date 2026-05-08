"use client";

import { create } from "zustand";

export type PickInteractionMode = "inactive" | "multi";

function sortUnique(ids: Iterable<number>): number[] {
  return [...new Set(ids)].filter((n) => Number.isFinite(n)).sort((a, b) => a - b);
}

type MultiSelectState = {
  pickInteractionMode: PickInteractionMode;
  selectedLocalIds: number[];
  enterMultiSelect: () => void;
  exitMultiSelect: () => void;
  /** End session, clear ids (caller clears viewer highlight if needed). */
  exitMultiSelectSession: () => void;
  clearSelected: () => void;
  toggleLocalIds: (ids: number[]) => void;
  reset: () => void;
};

const initial = {
  pickInteractionMode: "inactive" as PickInteractionMode,
  selectedLocalIds: [] as number[],
};

export const useMultiSelectStore = create<MultiSelectState>((set, get) => ({
  ...initial,
  enterMultiSelect: () => set({ pickInteractionMode: "multi" }),
  exitMultiSelect: () => set({ pickInteractionMode: "inactive" }),
  exitMultiSelectSession: () => set({ pickInteractionMode: "inactive", selectedLocalIds: [] }),
  clearSelected: () => set({ selectedLocalIds: [] }),
  toggleLocalIds: (ids) => {
    const raw = [...new Set(ids)].filter((n) => Number.isFinite(n));
    if (raw.length === 0) return;
    const cur = get().selectedLocalIds;
    const curSet = new Set(cur);
    const allIn = raw.every((id) => curSet.has(id));
    const nextSet = new Set(cur);
    if (allIn) {
      for (const id of raw) nextSet.delete(id);
    } else {
      for (const id of raw) nextSet.add(id);
    }
    set({ selectedLocalIds: sortUnique(nextSet) });
  },
  reset: () => set(initial),
}));
