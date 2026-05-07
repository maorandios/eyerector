import * as THREE from "three";

/**
 * Viewer world is Three.js **Y-up** (floor XZ, vertical Y). IFC fragments apply RX(-90) placement — keep axes consistent with {@link ViewerEngine.setupWorld}.
 */
export type ViewModeId = "top" | "bottom" | "right" | "left" | "front" | "back";

export const VIEW_MODE_ORDER: ViewModeId[] = [
  "top",
  "bottom",
  "right",
  "left",
  "front",
  "back",
];

export const VIEW_MODE_LABELS_HE: Record<ViewModeId, string> = {
  top: "על",
  bottom: "תחתית",
  right: "ימין",
  left: "שמאל",
  front: "קדימה",
  back: "אחורה",
};

/** Normalized direction from model center toward camera position (world space). */
export function eyeDirectionWorld(mode: ViewModeId): THREE.Vector3 {
  switch (mode) {
    case "top":
      return new THREE.Vector3(0, 1, 0);
    case "bottom":
      return new THREE.Vector3(0, -1, 0);
    case "right":
      return new THREE.Vector3(1, 0, 0);
    case "left":
      return new THREE.Vector3(-1, 0, 0);
    case "front":
      return new THREE.Vector3(0, 0, 1);
    case "back":
      return new THREE.Vector3(0, 0, -1);
  }
}

export function cameraUpForViewMode(mode: ViewModeId): THREE.Vector3 {
  switch (mode) {
    case "top":
    case "bottom":
      return new THREE.Vector3(0, 0, 1);
    case "right":
    case "left":
    case "front":
    case "back":
      return new THREE.Vector3(0, 1, 0);
  }
}

export function eyePositionFromCenter(
  mode: ViewModeId,
  center: THREE.Vector3,
  distance: number,
  target = new THREE.Vector3(),
): THREE.Vector3 {
  return target.copy(eyeDirectionWorld(mode)).multiplyScalar(distance).add(center);
}
