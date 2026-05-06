export type ViewerMode = "management" | "production" | "installation";

export type ElementCategory =
  | "assemblies"
  | "beams"
  | "columns"
  | "plates"
  | "bolts"
  | "other";

export interface Element {
  expressId: number;
  ifcType: string;
  name?: string;
  assemblyMark?: string;
  partMark?: string;
  profile?: string;
  material?: string;
  weightKg?: number;
  lengthMm?: number;
  dimensions?: string;
  category: ElementCategory;
}

export interface Part {
  expressId: number;
  mark?: string;
  type: string;
  profile?: string;
  material?: string;
  lengthMm?: number;
  dimensions?: string;
  weightKg?: number;
}

export interface Assembly {
  id: string;
  mark?: string;
  name?: string;
  expressIds: number[];
  weightKg?: number;
  partCount: number;
  parts: Part[];
}
