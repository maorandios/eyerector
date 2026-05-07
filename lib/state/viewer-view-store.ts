"use client";

import { create } from "zustand";
import type { ViewModeId } from "@/lib/viewer/view-mode-presets";

export type ViewerCameraMode = "perspective" | "orthographic";

interface ViewerViewState {
  /** Active orthographic preset, or indication idle when perspective-only navigation. */
  viewMode: ViewModeId | "none";
  cameraMode: ViewerCameraMode;
  setOrthographicView: (mode: ViewModeId) => void;
  clearView: () => void;
}

export const useViewerViewStore = create<ViewerViewState>((set) => ({
  viewMode: "none",
  cameraMode: "perspective",

  setOrthographicView: (mode: ViewModeId) =>
    set({ viewMode: mode, cameraMode: "orthographic" }),

  clearView: () => set({ viewMode: "none", cameraMode: "perspective" }),
}));
