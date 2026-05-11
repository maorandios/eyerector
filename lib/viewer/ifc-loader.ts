import * as OBC from "@thatopen/components";
import * as WEBIFC from "web-ifc";

const ifcLoaderSetupByComponents = new WeakMap<OBC.Components, Promise<void>>();

function ensureIfcLoaderWasmSetup(components: OBC.Components): Promise<void> {
  let p = ifcLoaderSetupByComponents.get(components);
  if (!p) {
    const ifcLoader = components.get(OBC.IfcLoader);
    p = ifcLoader.setup({
      autoSetWasm: false,
      wasm: {
        path: "https://unpkg.com/web-ifc@0.0.77/",
        absolute: true,
      },
      customLocateFileHandler: (url) => {
        if (url.endsWith(".wasm")) {
          return `https://unpkg.com/web-ifc@0.0.77/${url.split("/").pop()}`;
        }
        return url;
      },
    });
    ifcLoaderSetupByComponents.set(components, p);
  }
  return p;
}

export class IfcLoadError extends Error {
  readonly fileName: string;
  constructor(message: string, fileName: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "IfcLoadError";
    this.fileName = fileName;
  }
}

export async function loadIfcModel(
  components: OBC.Components,
  file: File,
): Promise<{ model: unknown; data: Uint8Array }> {
  const buffer = await file.arrayBuffer();
  const data = new Uint8Array(buffer);

  const fragments = components.get(OBC.FragmentsManager);
  if (!fragments.initialized) {
    fragments.init(await OBC.FragmentsManager.getWorker());
    /**
     * Default maxUpdateRate (100 ms) drops {@link FRAGS.FragmentsModels.update} calls while the
     * camera is idle — Clipper/slider plane edits then never reach the worker (cuts look broken).
     */
    fragments.core.settings.maxUpdateRate = 0;
  }

  await ensureIfcLoaderWasmSetup(components);
  const ifcLoader = components.get(OBC.IfcLoader);

  try {
    const model = await ifcLoader.load(data, true, file.name, {
      instanceCallback: (importer) => {
        importer.classes.elements.delete(WEBIFC.IFCGRID);
        importer.classes.elements.delete(WEBIFC.IFCGRIDAXIS);
        importer.classes.elements.delete(WEBIFC.IFCGRIDPLACEMENT);
      },
    });
    return { model, data };
  } catch (err) {
    const msg =
      "לא ניתן לקרוא את קובץ ה-IFC הזה (ייתכן ששמור מייצא חסר או לא תקין). נסה לייצא מחדש מהמודל.";
    console.error("IFC load failed:", file.name, err);
    throw new IfcLoadError(msg, file.name, err instanceof Error ? { cause: err } : undefined);
  }
}
