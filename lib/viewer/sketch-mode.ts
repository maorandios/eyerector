import * as THREE from "three";

export const SKETCH_EDGE_CHILD_NAME = "eyeSteel-sketch-edges";

/** Instanced fragment tiles: wireframe overlay InstancedMesh (see userData key). */
export const SKETCH_INSTANCED_EDGE_USERDATA = "eyeSteelSketchInstancedEdgeMesh";
const SKETCH_INSTANCED_ONBEFORE_PREV = "eyeSteelSketchInstancedEdgeOnBeforePrev";

/** Dark gray CAD-style strokes (only visible tint in sketch mode — solids are transparent). */
export const SKETCH_EDGE_HEX = 0x2c2c2c;

/** Fewer segments on curved steel for tablet FPS (degrees). */
export const SKETCH_EDGE_THRESHOLD_DEG = 34;

/** Faces invisible; outlines carry the sketch — keeps scene backdrop + lighting unchanged. */
export function createSketchFillMaterial(): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    toneMapped: false,
  });
}

/** Non-instanced meshes: `LineSegments` + this material (valid only for lines). */
export function createSketchLineMaterial(): THREE.LineBasicMaterial {
  return new THREE.LineBasicMaterial({
    color: SKETCH_EDGE_HEX,
    toneMapped: false,
  });
}

/**
 * Fallback when an instanced mesh does not use That Open {@link isLodFragmentMaterial}
 * (standard positions — safe for `MeshBasicMaterial` wireframe).
 */
function createSketchWireframeMaterial(): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color: SKETCH_EDGE_HEX,
    wireframe: true,
    toneMapped: false,
    depthTest: false,
  });
}

/** That Open fragment tiles use {@link LodMaterial} — opacity lives on uniforms, not mesh.material swaps. */
export function isLodFragmentMaterial(m: THREE.Material): boolean {
  return Boolean((m as THREE.Material & { isLodMaterial?: boolean }).isLodMaterial);
}

type LodLikeMaterial = THREE.ShaderMaterial & {
  isLodMaterial?: boolean;
  lodOpacity: number;
  lodColor: THREE.Color;
  lodSize: THREE.Vector2;
};

function syncLodSketchOverlayFromSource(dst: THREE.Material, src: THREE.Material): void {
  if (!isLodFragmentMaterial(dst) || !isLodFragmentMaterial(src)) return;
  (dst as LodLikeMaterial).lodSize.copy((src as LodLikeMaterial).lodSize);
}

function cloneSketchInstancedOverlayMaterial(source: THREE.Material): THREE.Material {
  if (isLodFragmentMaterial(source)) {
    const c = source.clone() as LodLikeMaterial;
    c.wireframe = true;
    c.lodOpacity = 1;
    c.lodColor = new THREE.Color(SKETCH_EDGE_HEX);
    return c;
  }
  return createSketchWireframeMaterial();
}

function cloneSketchInstancedOverlayMaterials(
  source: THREE.Material | THREE.Material[],
): THREE.Material | THREE.Material[] {
  return Array.isArray(source) ? source.map(cloneSketchInstancedOverlayMaterial) : cloneSketchInstancedOverlayMaterial(source);
}

function disposeSidecarMaterials(material: THREE.Material | THREE.Material[]): void {
  if (Array.isArray(material)) {
    for (const m of material) m.dispose();
  } else {
    material.dispose();
  }
}

function disposeInstancedSketchSidecar(im: THREE.InstancedMesh): void {
  const ud = im.userData as Record<string, unknown>;
  const hadEdge = SKETCH_INSTANCED_EDGE_USERDATA in ud;
  const hadPrev = SKETCH_INSTANCED_ONBEFORE_PREV in ud;
  if (!hadEdge && !hadPrev) return;

  const wireIm = ud[SKETCH_INSTANCED_EDGE_USERDATA] as THREE.InstancedMesh | undefined;
  const prevOnBefore = ud[SKETCH_INSTANCED_ONBEFORE_PREV] as THREE.Object3D["onBeforeRender"] | undefined;

  if (wireIm) {
    wireIm.parent?.remove(wireIm);
    disposeSidecarMaterials(wireIm.material);
    // Geometry is shared with the source InstancedMesh — never dispose here.
  }
  delete ud[SKETCH_INSTANCED_EDGE_USERDATA];
  if (hadPrev) {
    im.onBeforeRender = prevOnBefore ?? (null as unknown as THREE.Object3D["onBeforeRender"]);
    delete ud[SKETCH_INSTANCED_ONBEFORE_PREV];
  }
}

/** Remove cached edge LineSegments from meshes under `root` and dispose their geometries. */
export function stripSketchEdgeChildren(root: THREE.Object3D): void {
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh & THREE.InstancedMesh;
    if (!mesh.isMesh) return;

    if (mesh.isInstancedMesh) {
      disposeInstancedSketchSidecar(mesh);
    }

    const removeList: THREE.Object3D[] = [];
    for (const ch of mesh.children) {
      if (ch.name === SKETCH_EDGE_CHILD_NAME) removeList.push(ch);
    }
    for (const ch of removeList) {
      mesh.remove(ch);
      const ls = ch as THREE.LineSegments;
      ls.geometry?.dispose();
    }
  });
}

/**
 * That Open LOD tiles encode final positions in a **custom vertex shader** (`LodMaterial`).
 * `MeshBasicMaterial` wireframe uses the built-in vertex path — garbage in clip space → sparse dots.
 * Use a **cloned** `LodMaterial` with `wireframe: true` and synced `lodSize` / instance matrices.
 */
function attachInstancedSketchWireframe(im: THREE.InstancedMesh): void {
  const geom = im.geometry as THREE.BufferGeometry | undefined;
  if (!geom?.attributes.position || geom.getAttribute("position").count < 3) return;
  if (im.count <= 0) return;

  const overlayMats = cloneSketchInstancedOverlayMaterials(im.material);
  const wireIm = new THREE.InstancedMesh(geom, overlayMats, im.count);
  wireIm.name = `${SKETCH_EDGE_CHILD_NAME}-instanced-lod-wire`;
  wireIm.frustumCulled = im.frustumCulled;
  wireIm.visible = false;
  wireIm.raycast = () => {};
  wireIm.renderOrder = 1;

  wireIm.instanceMatrix.array.set(im.instanceMatrix.array);
  wireIm.instanceMatrix.needsUpdate = true;

  const ud = im.userData as Record<string, unknown>;
  if (ud[SKETCH_INSTANCED_EDGE_USERDATA]) {
    disposeInstancedSketchSidecar(im);
  }

  const prevOnBefore = im.onBeforeRender;
  im.onBeforeRender = (renderer, scene, camera, geometry, material, group) => {
    if (prevOnBefore) prevOnBefore.call(im, renderer, scene, camera, geometry, material, group);

    wireIm.instanceMatrix.array.set(im.instanceMatrix.array);
    wireIm.instanceMatrix.needsUpdate = true;

    const sm = im.material;
    const wm = wireIm.material;
    if (Array.isArray(sm) && Array.isArray(wm)) {
      const n = Math.min(sm.length, wm.length);
      for (let i = 0; i < n; i++) syncLodSketchOverlayFromSource(wm[i], sm[i]);
    } else if (!Array.isArray(sm) && !Array.isArray(wm)) {
      syncLodSketchOverlayFromSource(wm, sm);
    }

    wireIm.boundingSphere = null;
  };
  ud[SKETCH_INSTANCED_ONBEFORE_PREV] = prevOnBefore ?? null;
  ud[SKETCH_INSTANCED_EDGE_USERDATA] = wireIm;

  im.parent?.add(wireIm);
}

/**
 * One-time: `LineSegments` under regular meshes; for {@link THREE.InstancedMesh} (That Open tiles),
 * a sibling wireframe InstancedMesh with cloned LOD shader material.
 */
export function attachSketchEdges(
  root: THREE.Object3D,
  lineMaterial: THREE.LineBasicMaterial,
  thresholdRad = THREE.MathUtils.degToRad(SKETCH_EDGE_THRESHOLD_DEG),
): void {
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh & THREE.InstancedMesh;
    if (!mesh.isMesh) return;

    if (mesh.isInstancedMesh) {
      attachInstancedSketchWireframe(mesh);
      return;
    }

    const geom = mesh.geometry as THREE.BufferGeometry | undefined;
    if (!geom || !geom.attributes.position) return;
    if (geom.getAttribute("position").count < 3) return;

    try {
      const edgesGeom = new THREE.EdgesGeometry(geom, thresholdRad);
      const lines = new THREE.LineSegments(edgesGeom, lineMaterial);
      lines.name = SKETCH_EDGE_CHILD_NAME;
      lines.raycast = () => {};
      lines.visible = false;
      lines.frustumCulled = mesh.frustumCulled;
      lines.renderOrder = 1;
      mesh.add(lines);
    } catch {
      try {
        const wireGeom = new THREE.WireframeGeometry(geom);
        const lines = new THREE.LineSegments(wireGeom, lineMaterial);
        lines.name = SKETCH_EDGE_CHILD_NAME;
        lines.raycast = () => {};
        lines.visible = false;
        lines.frustumCulled = mesh.frustumCulled;
        lines.renderOrder = 1;
        mesh.add(lines);
      } catch {
        /* degenerate / exotic buffers */
      }
    }
  });
}

/** Show or hide sketch outlines for both LineSegments children and instanced wireframe sidecars. */
export function setSketchEdgeVisibility(root: THREE.Object3D, visible: boolean): void {
  root.traverse((obj) => {
    for (const ch of obj.children) {
      if (ch.name === SKETCH_EDGE_CHILD_NAME) ch.visible = visible;
    }
    const mesh = obj as THREE.InstancedMesh;
    if (mesh.isInstancedMesh) {
      const wireIm = mesh.userData[SKETCH_INSTANCED_EDGE_USERDATA] as THREE.InstancedMesh | undefined;
      if (wireIm) wireIm.visible = visible;
    }
  });
}
