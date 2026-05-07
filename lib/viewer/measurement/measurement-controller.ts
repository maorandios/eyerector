"use client";

import * as THREE from "three";
import * as FRAGS from "@thatopen/fragments";
import * as OBC from "@thatopen/components";
import type { DimensionLine } from "@thatopen/components-front";
import * as OBF from "@thatopen/components-front";
import { MeasurementHtmlOverlay, hideThatOpenDimensionCss2d } from "@/lib/viewer/measurement/measurement-html-overlay";

type Css2dMarkLike = {
  visible: boolean;
  three: { element: unknown };
};

/** Dark gray for dimension line + badge (That Open `linesMaterial` + HTML overlay). */
const MEASUREMENT_DIM_GRAY = 0x404040;

function createHiddenMeasurementEndpointElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.setAttribute("data-eyeSteel-measurement-endpoint", "true");
  el.style.cssText =
    "box-sizing:border-box;width:0;height:0;margin:0;padding:0;border:0;" +
    "opacity:0;visibility:hidden;pointer-events:none;overflow:hidden;";
  return el;
}

/**
 * Thin wrapper around That Open {@link OBF.LengthMeasurement}.
 * Keeps configuration out of {@link ViewerEngine} and avoids coupling to selection.
 */
export class MeasurementController {
  private measurer: OBF.LengthMeasurement | null = null;
  private configured = false;
  private attachedWorld: OBC.World | null = null;
  private htmlOverlay: MeasurementHtmlOverlay | null = null;

  constructor(private readonly components: OBC.Components) {}

  private ensure(): OBF.LengthMeasurement {
    if (!this.measurer) {
      this.measurer = this.components.get(OBF.LengthMeasurement);
    }
    const m = this.measurer;
    if (!this.configured) {
      m.mode = "free";
      m.snappings = [FRAGS.SnappingClass.POINT];
      m.units = "mm";
      m.rounding = 1;
      /** MOUSE_MOVE: marker tracks finger between taps (friendlier on touch). For huge IFCs, try MOUSE_STOP + higher delay. */
      m.pickMode = OBF.MeasurementPickMode.MOUSE_MOVE;
      m.delay = 140;
      m.color = new THREE.Color(MEASUREMENT_DIM_GRAY);
      m.linesEndpointElement = createHiddenMeasurementEndpointElement();
      m.pickerSize = 14;
      // Do not set `enabled` / `visible` here: Measurement.setEvents requires world first.
      this.configured = true;
    }
    return m;
  }

  /** Assign world before activate (same instance as the IFC viewer). */
  attach(world: OBC.World) {
    const m = this.ensure();
    m.world = world;
    m.visible = false;
    m.enabled = false;
    this.attachedWorld = world;
    const parent = world.renderer?.three?.domElement?.parentElement;
    if (parent instanceof HTMLElement) {
      this.htmlOverlay?.dispose();
      this.htmlOverlay = new MeasurementHtmlOverlay(parent);
    }
  }

  /**
   * Hide the library snap marker (CSS2D dot). Run every frame — when measurement mode is off the
   * picker can still leave the last marker visible (offset/glitched vs our DOM overlay).
   */
  suppressVertexPickerMarker() {
    if (!this.measurer) return;
    const picker = (
      this.measurer as unknown as {
        _vertexPicker?: { marker?: Css2dMarkLike | null };
      }
    )._vertexPicker;
    const marker = picker?.marker;
    if (!marker) return;
    marker.visible = false;
    const el = marker.three.element;
    if (el instanceof HTMLElement) {
      el.style.display = "none";
      el.style.visibility = "hidden";
      el.style.opacity = "0";
      el.style.pointerEvents = "none";
    }
  }

  /** In-progress segment uses the same CSS2D endpoints/label as committed lines. */
  private hidePreviewDimensionCss2d() {
    const dim = (this.measurer as unknown as { _temp?: { dimension?: DimensionLine } })._temp
      ?.dimension;
    if (dim) hideThatOpenDimensionCss2d(dim);
  }

  /** Call each frame after render so HTML badges track the camera (CSS2D labels stay hidden). */
  syncHtmlLabels() {
    if (!this.measurer || !this.attachedWorld?.renderer?.three?.domElement) return;
    this.suppressVertexPickerMarker();
    this.hidePreviewDimensionCss2d();
    const canvas = this.attachedWorld.renderer.three.domElement;
    const camera = this.attachedWorld.camera?.three;
    if (!camera || !this.htmlOverlay) return;
    const preview = (this.measurer as unknown as { _temp?: { dimension?: DimensionLine } })._temp
      ?.dimension;
    const lines = preview ? [...this.measurer.lines, preview] : this.measurer.lines;
    this.htmlOverlay.sync(lines, camera, canvas);
  }

  activate() {
    const m = this.ensure();
    m.visible = true;
    m.enabled = true;
  }

  deactivate() {
    if (!this.measurer) return;
    this.measurer.cancelCreation();
    this.measurer.enabled = false;
  }

  /** Two taps => two {@link OBF.LengthMeasurement.create} calls complete one segment (library contract). */
  async tapCommit() {
    const m = this.ensure();
    if (!m.enabled) return;
    await m.create();
  }

  clearAll() {
    if (!this.measurer) return;
    this.measurer.cancelCreation();
    this.measurer.list.clear();
    this.htmlOverlay?.clearDom();
  }

  /**
   * Disable measurement when disposing the viewer. Do not dispose the singleton
   * returned by {@link OBC.Components.get}(LengthMeasurement).
   */
  shutdown() {
    this.htmlOverlay?.dispose();
    this.htmlOverlay = null;
    this.attachedWorld = null;
    if (!this.measurer) return;
    this.measurer.cancelCreation();
    this.measurer.enabled = false;
    this.measurer.visible = false;
    this.measurer.world = null;
  }
}
