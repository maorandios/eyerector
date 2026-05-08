"use client";

import * as THREE from "three";
import type { FragmentsModel, MeshData } from "@thatopen/fragments";
import { CONTEXT_GHOST_SNAPSHOT_NAME } from "@/lib/viewer/visual-policy";
import {
  SKETCH_EDGE_THRESHOLD_DEG,
  getOrCreateSketchEdgeLineMaterial,
  isLodFragmentMaterial,
} from "@/lib/viewer/sketch-mode";

/** Group under `model.object` — only picked locals while **בודד** / **הצג בהקשר** (tile sketch edges stay off). */
export const ISOLATION_SELECTION_EDGE_GROUP = "eyeSteel-isolation-selection-edges";

const GEOM_CHUNK = 48;
const FALLBACK_IFC_FACE = new THREE.Color(0x9ca3af);

type LodLikeMaterial = THREE.ShaderMaterial & { lodColor: THREE.Color };

/**
 * Live tile face tint (`lodColor`) keyed by internal **itemId** (see mesh `userData.itemId`).
 * When {@link FragmentsModel.visibleItems} is populated, only those tiles are considered.
 */
function collectItemIdToLodFaceColor(modelRoot: THREE.Object3D, fragModel: FragmentsModel): Map<number, THREE.Color> {
  const itemIdToFace = new Map<number, THREE.Color>();
  const vis = fragModel.visibleItems;
  const useVis = vis.size > 0;
  modelRoot.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh) && !(obj instanceof THREE.InstancedMesh)) return;
    if (obj.name === CONTEXT_GHOST_SNAPSHOT_NAME || obj.name.startsWith(ISOLATION_SELECTION_EDGE_GROUP)) {
      return;
    }
    const ud = obj.userData as { itemId?: unknown };
    if (typeof ud.itemId !== "number" || !Number.isFinite(ud.itemId)) return;
    if (useVis && !vis.has(ud.itemId)) return;
    const mats = obj.material;
    const m0 = Array.isArray(mats) ? mats[0] : mats;
    if (!m0 || !isLodFragmentMaterial(m0)) return;
    const face = (m0 as LodLikeMaterial).lodColor.clone();
    if (!itemIdToFace.has(ud.itemId)) itemIdToFace.set(ud.itemId, face);
  });
  return itemIdToFace;
}

const ITEM_ID_RESOLVE_CONCURRENCY = 14;

/**
 * Map worker **itemId** → user **localId** via {@link FragmentsModel.getLocalIdsFromItemIds}
 * (main-thread API). Matches normal sketch edges, which read `lodColor` from the same tiles.
 */
async function mapLodFaceColorsToLocalIds(
  fragModel: FragmentsModel,
  itemIdToFace: Map<number, THREE.Color>,
  selectedLocals: ReadonlySet<number>,
): Promise<Map<number, THREE.Color>> {
  const byLocal = new Map<number, THREE.Color>();
  const itemIds = [...itemIdToFace.keys()];
  if (itemIds.length === 0 || selectedLocals.size === 0) return byLocal;

  for (let i = 0; i < itemIds.length; i += ITEM_ID_RESOLVE_CONCURRENCY) {
    const slice = itemIds.slice(i, i + ITEM_ID_RESOLVE_CONCURRENCY);
    await Promise.all(
      slice.map(async (itemId) => {
        let locals: number[] = [];
        try {
          locals = await fragModel.getLocalIdsFromItemIds([itemId]);
        } catch {
          return;
        }
        const c = itemIdToFace.get(itemId);
        if (!c) return;
        for (const lid of locals) {
          if (!selectedLocals.has(lid)) continue;
          if (!byLocal.has(lid)) byLocal.set(lid, c.clone());
        }
      }),
    );
  }
  return byLocal;
}

function toUint32IndexArray(raw: NonNullable<MeshData["indices"]>): Uint32Array {
  if (raw instanceof Uint32Array) return raw;
  const out = new Uint32Array(raw.length);
  out.set(raw);
  return out;
}

function meshDataToBufferGeometry(mesh: MeshData): THREE.BufferGeometry | null {
  if (!mesh.positions || mesh.positions.length < 9) return null;
  const geom = new THREE.BufferGeometry();
  const pos = Float32Array.from(mesh.positions);
  geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  if (mesh.indices && mesh.indices.length >= 3) {
    const arr = toUint32IndexArray(mesh.indices);
    geom.setIndex(new THREE.BufferAttribute(arr, 1));
  }
  if (mesh.transform) {
    geom.applyMatrix4(mesh.transform);
  }
  geom.computeBoundingSphere();
  return geom;
}

/**
 * Line-only overlay for the given fragment **local** ids (IFC face tint → darkened edge stroke,
 * same rule as default sketch edges). Independent of tile LOD wire sidecars so isolation/context
 * can hide global sketch lines without losing outlines on the picked element(s).
 */
export async function buildIsolationSelectionEdgeLines(
  fragModel: FragmentsModel,
  modelObject: THREE.Object3D,
  selectedLocalIds: readonly number[],
  lineMaterialPool: Map<number, THREE.LineBasicMaterial>,
): Promise<THREE.Group> {
  const group = new THREE.Group();
  group.name = ISOLATION_SELECTION_EDGE_GROUP;
  const ids = [...new Set(selectedLocalIds)].filter((id) => Number.isFinite(id));
  if (ids.length === 0) return group;

  const itemIdToFace = collectItemIdToLodFaceColor(modelObject, fragModel);
  const lodFaceByLocal = await mapLodFaceColorsToLocalIds(fragModel, itemIdToFace, new Set(ids));

  const colorByLocalFallback = new Map<number, THREE.Color>();
  for (let i = 0; i < ids.length; i += GEOM_CHUNK) {
    const slice = ids.slice(i, i + GEOM_CHUNK);
    try {
      const blocks = await fragModel.getItemsMaterialDefinition(slice);
      for (const block of blocks) {
        const c = block.definition.color.clone();
        for (const lid of block.localIds) {
          if (!lodFaceByLocal.has(lid)) colorByLocalFallback.set(lid, c);
        }
      }
    } catch {
      /* materials optional per slice */
    }
  }

  const threshold = THREE.MathUtils.degToRad(SKETCH_EDGE_THRESHOLD_DEG);

  for (let i = 0; i < ids.length; i += GEOM_CHUNK) {
    const slice = ids.slice(i, i + GEOM_CHUNK);
    let itemGeoms: MeshData[][];
    try {
      itemGeoms = await fragModel.getItemsGeometry(slice, 0 /* CurrentLod.GEOMETRY */);
    } catch {
      continue;
    }
    for (let j = 0; j < slice.length; j++) {
      const localId = slice[j];
      const chunks = itemGeoms[j];
      if (!chunks?.length) continue;
      for (const mesh of chunks) {
        const chunkLid = typeof mesh.localId === "number" ? mesh.localId : localId;
        const chunkFace =
          lodFaceByLocal.get(chunkLid) ??
          colorByLocalFallback.get(chunkLid) ??
          lodFaceByLocal.get(localId) ??
          colorByLocalFallback.get(localId) ??
          FALLBACK_IFC_FACE;
        const chunkMat = getOrCreateSketchEdgeLineMaterial(lineMaterialPool, chunkFace);
        const g = meshDataToBufferGeometry(mesh);
        if (!g) continue;
        let linesGeom: THREE.EdgesGeometry | THREE.WireframeGeometry;
        try {
          linesGeom = new THREE.EdgesGeometry(g, threshold);
        } catch {
          try {
            linesGeom = new THREE.WireframeGeometry(g);
          } catch {
            g.dispose();
            continue;
          }
        }
        g.dispose();
        const lines = new THREE.LineSegments(linesGeom, chunkMat);
        lines.name = `${ISOLATION_SELECTION_EDGE_GROUP}-line`;
        lines.raycast = () => {};
        lines.frustumCulled = true;
        lines.renderOrder = 2;
        group.add(lines);
      }
    }
  }

  return group;
}
