import type { Assembly, Element, Part } from "@/types/domain";

export function buildAssemblies(elements: Element[]): Assembly[] {
  const byMark = new Map<string, Element[]>();
  for (const element of elements) {
    const mark = element.assemblyMark || "ללא סימון";
    const list = byMark.get(mark) ?? [];
    list.push(element);
    byMark.set(mark, list);
  }

  return Array.from(byMark.entries()).map(([mark, list], idx) => {
    const parts: Part[] = list.map((el) => ({
      expressId: el.expressId,
      mark: el.partMark,
      type: el.ifcType,
      profile: el.profile,
      material: el.material,
      lengthMm: el.lengthMm,
      dimensions: el.dimensions,
      weightKg: el.weightKg,
    }));
    return {
      id: `asm-${idx + 1}`,
      mark,
      name: list[0]?.name,
      expressIds: list.map((el) => el.expressId),
      weightKg: parts.reduce((sum, p) => sum + (p.weightKg ?? 0), 0),
      partCount: parts.length,
      parts,
    };
  });
}
