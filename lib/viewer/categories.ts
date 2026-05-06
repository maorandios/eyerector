import type { ElementCategory } from "@/types/domain";

export function mapIfcTypeToCategory(ifcType: string): ElementCategory {
  const t = ifcType.toLowerCase();
  if (t.includes("assembly")) return "assemblies";
  if (t.includes("beam") || t.includes("member")) return "beams";
  if (t.includes("column")) return "columns";
  if (t.includes("plate")) return "plates";
  if (t.includes("fastener") || t.includes("bolt")) return "bolts";
  return "other";
}
