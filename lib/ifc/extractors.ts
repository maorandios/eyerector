import type { Element } from "@/types/domain";
import { mapIfcTypeToCategory } from "@/lib/viewer/categories";

export function extractElement(raw: {
  expressId: number;
  ifcType: string;
  name?: string;
  [key: string]: unknown;
}): Element {
  return {
    expressId: raw.expressId,
    ifcType: raw.ifcType,
    name: String(raw.name ?? ""),
    assemblyMark: String(raw.ASSEMBLY_POS ?? raw.assemblyMark ?? ""),
    partMark: String(raw.PART_POS ?? raw.partMark ?? ""),
    profile: String(raw.PROFILE ?? raw.profile ?? ""),
    material: String(raw.MATERIAL ?? raw.material ?? ""),
    weightKg: toNumber(raw.WEIGHT ?? raw.weightKg),
    lengthMm: toNumber(raw.LENGTH ?? raw.lengthMm),
    dimensions: String(raw.dimensions ?? ""),
    category: mapIfcTypeToCategory(raw.ifcType),
  };
}

function toNumber(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}
