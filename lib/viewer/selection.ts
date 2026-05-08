import * as OBC from "@thatopen/components";

import { buildSelectionHighlightMaterial } from "@/lib/viewer/visual-policy";

export async function highlightExpressIds(
  components: OBC.Components,
  modelId: string,
  expressIds: number[],
) {
  const fragments = components.get(OBC.FragmentsManager);
  await fragments.highlight(buildSelectionHighlightMaterial(), { [modelId]: new Set(expressIds) });
}

export async function clearHighlight(components: OBC.Components) {
  const fragments = components.get(OBC.FragmentsManager);
  await fragments.resetHighlight();
}
