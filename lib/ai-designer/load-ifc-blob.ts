import { IfcLoadError } from "@/lib/viewer/ifc-loader";
import type { ViewerEngine } from "@/lib/viewer/engine";

const AI_IFC_FILE_NAME = "ai-generated.ifc";

/**
 * Clears the current scene, loads IFC bytes from a Blob, and revokes any object URL when done.
 */
export async function loadIfcBlobIntoViewer(
  engine: ViewerEngine,
  ifcBlob: Blob,
  objectUrl?: string,
): Promise<void> {
  const file = new File([ifcBlob], AI_IFC_FILE_NAME, {
    type: "application/octet-stream",
  });

  try {
    await engine.clearModel();
    await engine.loadFile(file);
  } catch (err) {
    if (err instanceof IfcLoadError) {
      throw err;
    }
    throw err instanceof Error ? err : new Error("Failed to load generated IFC in viewer");
  } finally {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
    }
  }
}

export function createIfcObjectUrl(ifcBlob: Blob): string {
  return URL.createObjectURL(ifcBlob);
}
