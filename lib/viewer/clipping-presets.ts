import * as THREE from "three";
import {
  VIEW_MODE_LABELS_HE,
  VIEW_MODE_ORDER,
  type ViewModeId,
} from "@/lib/viewer/view-mode-presets";

/**
 * Same six directions as מבט presets — **Y-up world** (floor XZ, vertical +Y).
 * Clipping normal points toward the half-space that gets **discarded** by Three.js
 * (`n·x + constant < 0`), chosen so the first cut through the bbox center roughly
 * splits the model (same axis semantics as `eyeDirectionWorld` / camera side).
 */
export type ClippingDirectionId = ViewModeId;

export const CLIPPING_DIRECTION_ORDER: ClippingDirectionId[] = VIEW_MODE_ORDER;

export const CLIPPING_LABELS_HE: Record<ClippingDirectionId, string> = VIEW_MODE_LABELS_HE;

/** Serializable mirror for UI / Zustand — engine owns the live `THREE.Plane`. */
export type ViewerClippingUiSnapshot = {
  active: boolean;
  direction: ClippingDirectionId | null;
  labelHe: string | null;
  depthOffset: number;
  depthMin: number;
  depthMax: number;
  flipped: boolean;
};

/** Unit outward normals for “clip from this side” (high camera side removed first). */
export function normalForClippingDirection(id: ClippingDirectionId, target = new THREE.Vector3()): THREE.Vector3 {
  switch (id) {
    case "top":
      return target.set(0, -1, 0);
    case "bottom":
      return target.set(0, 1, 0);
    case "right":
      return target.set(-1, 0, 0);
    case "left":
      return target.set(1, 0, 0);
    case "front":
      return target.set(0, 0, -1);
    case "back":
      return target.set(0, 0, 1);
  }
}
