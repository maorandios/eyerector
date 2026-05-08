import * as THREE from "three";

export const SKETCH_EDGE_CHILD_NAME = "eyeSteel-sketch-edges";

/** Instanced fragment tiles: wireframe overlay InstancedMesh (see userData key). */
export const SKETCH_INSTANCED_EDGE_USERDATA = "eyeSteelSketchInstancedEdgeMesh";

const EYE_STEEL_EDGE_BASE_MAT = "eyeSteelEdgeBaseMat";

export function restoreSelectionTintOnSketchLineSegments(root: THREE.Object3D): void {
  root.traverse((obj) => {
    for (const ch of obj.children) {
      if (ch.name !== SKETCH_EDGE_CHILD_NAME) continue;
      const ls = ch as THREE.LineSegments;
      const base = (ls.userData as Record<string, unknown>)[EYE_STEEL_EDGE_BASE_MAT] as
        | THREE.Material
        | undefined;
      if (base) {
        ls.material = base;
        delete (ls.userData as Record<string, unknown>)[EYE_STEEL_EDGE_BASE_MAT];
      }
    }
  });
}
const SKETCH_INSTANCED_ONBEFORE_PREV = "eyeSteelSketchInstancedEdgeOnBeforePrev";

/** IFC / fragment face tint → edge line: same hue, linear darken (see {@link edgeLineColorFromFace}). */
const EDGE_LINE_DARKEN = 0.48;

/** Fallback face tint when no color is readable on the material. */
const EDGE_FALLBACK_FACE_HEX = 0x9ca3af;

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

/** Darker variant of the element face color (same hue; multiply RGB by 0.48; floor for visibility). */
export function edgeLineColorFromFace(face: THREE.Color): THREE.Color {
  const out = face.clone().multiplyScalar(EDGE_LINE_DARKEN);
  const min = 0.05;
  if (out.r <= min && out.g <= min && out.b <= min) {
    out.setRGB(min, min, min);
  }
  return out;
}

function baseFaceColorFromMaterial(m: THREE.Material): THREE.Color {
  if (isLodFragmentMaterial(m)) {
    return (m as LodLikeMaterial).lodColor.clone();
  }
  if (
    m instanceof THREE.MeshStandardMaterial ||
    m instanceof THREE.MeshLambertMaterial ||
    m instanceof THREE.MeshPhongMaterial
  ) {
    return m.color.clone();
  }
  const c = (m as { color?: unknown }).color;
  if (c instanceof THREE.Color) return c.clone();
  return new THREE.Color(EDGE_FALLBACK_FACE_HEX);
}

function meshPrimaryFaceColor(mesh: THREE.Mesh): THREE.Color {
  const mats = mesh.material;
  const m0 = Array.isArray(mats) ? mats[0] : mats;
  if (!m0) return new THREE.Color(EDGE_FALLBACK_FACE_HEX);
  return baseFaceColorFromMaterial(m0);
}

function createEdgeLineMaterial(lineRgb: THREE.Color): THREE.LineBasicMaterial {
  return new THREE.LineBasicMaterial({
    color: lineRgb.clone(),
    toneMapped: false,
    depthTest: true,
    depthWrite: true,
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1,
  });
}

function getOrCreateEdgeLineMaterial(
  pool: Map<number, THREE.LineBasicMaterial>,
  face: THREE.Color,
): THREE.LineBasicMaterial {
  const edge = edgeLineColorFromFace(face);
  const k = edge.getHex();
  let m = pool.get(k);
  if (!m) {
    m = createEdgeLineMaterial(edge);
    pool.set(k, m);
  }
  return m;
}

/** `LineSegments` under a non-instanced mesh when it has no sketch edge child yet. */
function tryAttachNonInstancedSketchEdges(
  mesh: THREE.Mesh,
  lineMaterialPool: Map<number, THREE.LineBasicMaterial>,
  thresholdRad: number,
): boolean {
  if ((mesh as THREE.Mesh & THREE.InstancedMesh).isInstancedMesh) return false;
  if (mesh.children.some((c) => c.name === SKETCH_EDGE_CHILD_NAME)) return false;
  const geom = mesh.geometry as THREE.BufferGeometry | undefined;
  if (!geom || !geom.attributes.position) return false;
  if (geom.getAttribute("position").count < 3) return false;
  if (!mesh.material) return false;

  const lineMaterial = getOrCreateEdgeLineMaterial(lineMaterialPool, meshPrimaryFaceColor(mesh));

  try {
    const edgesGeom = new THREE.EdgesGeometry(geom, thresholdRad);
    const lines = new THREE.LineSegments(edgesGeom, lineMaterial);
    lines.name = SKETCH_EDGE_CHILD_NAME;
    lines.raycast = () => {};
    lines.visible = false;
    lines.frustumCulled = mesh.frustumCulled;
    lines.renderOrder = 1;
    mesh.add(lines);
    return true;
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
      return true;
    } catch {
      return false;
    }
  }
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

/**
 * Keep instanced LOD wireframe overlay in sync: edge “color” is live {@link LodLikeMaterial.lodColor}
 * darkened like regular mesh edges.
 */
function syncLodSketchWireframeFromSource(dst: THREE.Material, src: THREE.Material): void {
  if (!isLodFragmentMaterial(dst) || !isLodFragmentMaterial(src)) return;
  const d = dst as LodLikeMaterial;
  const s = src as LodLikeMaterial;
  d.lodSize.copy(s.lodSize);
  d.lodColor.copy(edgeLineColorFromFace(s.lodColor));
}

function createSketchWireframeMaterial(lineColor: THREE.Color): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color: lineColor.clone(),
    wireframe: true,
    toneMapped: false,
    depthTest: false,
  });
}

function cloneSketchInstancedOverlayMaterial(source: THREE.Material): THREE.Material {
  if (isLodFragmentMaterial(source)) {
    const c = source.clone() as LodLikeMaterial;
    c.wireframe = true;
    c.lodOpacity = 1;
    c.lodColor.copy(edgeLineColorFromFace((source as LodLikeMaterial).lodColor));
    return c;
  }
  const lineCol = edgeLineColorFromFace(baseFaceColorFromMaterial(source));
  return createSketchWireframeMaterial(lineCol);
}

function cloneSketchInstancedOverlayMaterials(
  source: THREE.Material | THREE.Material[],
): THREE.Material | THREE.Material[] {
  return Array.isArray(source)
    ? source.map(cloneSketchInstancedOverlayMaterial)
    : cloneSketchInstancedOverlayMaterial(source);
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
  const ud = im.userData as Record<string, unknown>;
  if (ud[SKETCH_INSTANCED_EDGE_USERDATA]) return;

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

  const prevOnBefore = im.onBeforeRender;
  im.onBeforeRender = (renderer, scene, camera, geometry, material, group) => {
    if (prevOnBefore) prevOnBefore.call(im, renderer, scene, camera, geometry, material, group);

    wireIm.instanceMatrix.array.set(im.instanceMatrix.array);
    wireIm.instanceMatrix.needsUpdate = true;

    const sm = im.material;
    const wm = wireIm.material;

    if (Array.isArray(sm) && Array.isArray(wm)) {
      const n = Math.min(sm.length, wm.length);
      for (let i = 0; i < n; i++) syncLodSketchWireframeFromSource(wm[i], sm[i]);
    } else if (!Array.isArray(sm) && !Array.isArray(wm)) {
      syncLodSketchWireframeFromSource(wm, sm);
    }

    wireIm.boundingSphere = null;
  };
  ud[SKETCH_INSTANCED_ONBEFORE_PREV] = prevOnBefore ?? null;
  ud[SKETCH_INSTANCED_EDGE_USERDATA] = wireIm;

  im.parent?.add(wireIm);
}

/**
 * New fragment tiles mounted after the first {@link attachSketchEdges} pass — attach outlines only
 * where missing. Call on each fragment model `onViewUpdated` while geometry streams in.
 * @returns Count of meshes that gained edge geometry in this pass.
 */
export function ensureSketchEdgesAttached(
  root: THREE.Object3D,
  lineMaterialPool: Map<number, THREE.LineBasicMaterial>,
  thresholdRad = THREE.MathUtils.degToRad(SKETCH_EDGE_THRESHOLD_DEG),
): number {
  let added = 0;
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh & THREE.InstancedMesh;
    if (!mesh.isMesh) return;
    const geom = mesh.geometry as THREE.BufferGeometry | undefined;
    if (!geom?.attributes.position || geom.getAttribute("position").count < 3) return;
    if (!mesh.material) return;

    if (mesh.isInstancedMesh) {
      if ((mesh.userData as Record<string, unknown>)[SKETCH_INSTANCED_EDGE_USERDATA]) return;
      attachInstancedSketchWireframe(mesh);
      if ((mesh.userData as Record<string, unknown>)[SKETCH_INSTANCED_EDGE_USERDATA]) added += 1;
      return;
    }
    if (tryAttachNonInstancedSketchEdges(mesh, lineMaterialPool, thresholdRad)) added += 1;
  });
  return added;
}

/**
 * Add edge geometry once per mesh: `LineSegments` + `EdgesGeometry` for plain meshes;
 * sibling wireframe {@link THREE.InstancedMesh} with cloned LOD shader material for That Open tiles.
 * `lineMaterialPool` keys darkened-edge hex → shared {@link THREE.LineBasicMaterial} per IFC color.
 */
export function attachSketchEdges(
  root: THREE.Object3D,
  lineMaterialPool: Map<number, THREE.LineBasicMaterial>,
  thresholdRad = THREE.MathUtils.degToRad(SKETCH_EDGE_THRESHOLD_DEG),
): void {
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh & THREE.InstancedMesh;
    if (!mesh.isMesh) return;

    if (mesh.isInstancedMesh) {
      attachInstancedSketchWireframe(mesh);
      return;
    }

    tryAttachNonInstancedSketchEdges(mesh, lineMaterialPool, thresholdRad);
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
