"use client";

import * as THREE from "three";
import * as OBC from "@thatopen/components";
import type { ViewerMode } from "@/types/domain";
import { loadIfcModel } from "@/lib/viewer/ifc-loader";

export class ViewerEngine {
  private readonly container: HTMLDivElement;
  private readonly components: OBC.Components;
  private world!: OBC.World;
  private animationHandle = 0;
  private modelObject: THREE.Object3D | null = null;
  private modelId: string | null = null;
  private disposed = false;

  constructor(container: HTMLDivElement) {
    this.container = container;
    this.components = new OBC.Components();
    this.setupWorld();
  }

  private setupWorld() {
    const worlds = this.components.get(OBC.Worlds);
    this.world = worlds.create<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>();
    this.world.scene = new OBC.SimpleScene(this.components);
    this.world.renderer = new OBC.SimpleRenderer(this.components, this.container);
    this.world.camera = new OBC.SimpleCamera(this.components);

    this.components.init();
    (this.world.scene as OBC.SimpleScene).setup();
    this.world.camera.controls?.setLookAt(18, 18, 18, 0, 0, 0);

    const light = new THREE.HemisphereLight(0xffffff, 0x111827, 0.8);
    this.world.scene.three.add(light);

    const grid = new THREE.GridHelper(200, 40, 0x3b82f6, 0x374151);
    this.world.scene.three.add(grid);

    this.animate();
  }

  async loadFile(file: File) {
    if (this.disposed) return;
    const { model } = await loadIfcModel(this.components, file);
    const casted = model as { modelId: string; object: THREE.Object3D };
    if (this.modelObject) this.world.scene.three.remove(this.modelObject);
    this.modelObject = casted.object;
    this.modelId = casted.modelId;
    this.world.scene.three.add(casted.object);
    this.fitAll();
  }

  getModelId() {
    return this.modelId;
  }

  setMode(mode: ViewerMode) {
    if (this.disposed) return;
    void mode;
    // Mode-specific visual behavior hooks are intentionally centralized here.
  }

  setCategoryVisible(category: string, visible: boolean) {
    if (this.disposed) return;
    void category;
    void visible;
    // Placeholder for category-level filtering.
  }

  setTransparency(enabled: boolean) {
    if (this.disposed) return;
    if (!this.modelObject) return;
    this.modelObject.traverse((child) => {
      const mesh = child as THREE.Mesh;
      const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
      if (!material) return;
      const setAlpha = (mat: THREE.Material) => {
        const m = mat as THREE.MeshStandardMaterial;
        m.transparent = enabled;
        m.opacity = enabled ? 0.35 : 1;
      };
      if (Array.isArray(material)) material.forEach(setAlpha);
      else setAlpha(material);
    });
  }

  resetView() {
    if (this.disposed) return;
    this.world.camera.controls?.setLookAt(18, 18, 18, 0, 0, 0, true);
  }

  fitAll() {
    if (this.disposed) return;
    if (!this.modelObject) return;
    const box = new THREE.Box3().setFromObject(this.modelObject);
    const center = box.getCenter(new THREE.Vector3());
    this.world.camera.controls?.setTarget(center.x, center.y, center.z, true);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.animationHandle);
    try {
      if (this.modelObject) {
        this.world.scene.three.remove(this.modelObject);
        this.modelObject = null;
      }
      this.world.renderer?.dispose();
      this.world.camera.controls?.dispose();
    } catch {
      // Guard against teardown edge-cases in React strict-mode remounts.
    }
  }

  private animate = () => {
    this.animationHandle = requestAnimationFrame(this.animate);
  };
}
