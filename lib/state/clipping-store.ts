"use client";

import { create } from "zustand";
import type { ViewerClippingUiSnapshot } from "@/lib/viewer/clipping-presets";

const inactive: ViewerClippingUiSnapshot = {
  active: false,
  direction: null,
  labelHe: null,
  depthOffset: 0,
  depthMin: 0,
  depthMax: 0,
  flipped: false,
};

type ClippingStore = ViewerClippingUiSnapshot & {
  /** True while user is in ortho “הצג כחתך” (not נבט-only); ביטול חתך restores perspective with clip on. */
  clipSectionOrthoActive: boolean;
  setClipSectionOrthoActive: (v: boolean) => void;
  syncFromEngine: (snapshot: ViewerClippingUiSnapshot) => void;
  reset: () => void;
};

export const useClippingStore = create<ClippingStore>((set) => ({
  ...inactive,
  clipSectionOrthoActive: false,
  setClipSectionOrthoActive: (v) => set({ clipSectionOrthoActive: v }),
  syncFromEngine: (snapshot) =>
    set((prev) => ({
      ...snapshot,
      clipSectionOrthoActive: snapshot.active ? prev.clipSectionOrthoActive : false,
    })),
  reset: () => set({ ...inactive, clipSectionOrthoActive: false }),
}));
