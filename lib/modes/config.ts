import type { ViewerMode } from "@/types/domain";
import { he } from "@/lib/i18n/he";

export const modeConfig: Record<
  ViewerMode,
  { label: string; actions: string[]; defaultTransparency: boolean }
> = {
  management: {
    label: he.management,
    actions: ["search", "filter", "isolate", "details"],
    defaultTransparency: false,
  },
  production: {
    label: he.production,
    actions: ["assemblySearch", "quickViews", "partsList", "isolateAssembly"],
    defaultTransparency: true,
  },
  installation: {
    label: he.installation,
    actions: ["contextIsolation", "categoryToggles", "transparency", "locate"],
    defaultTransparency: true,
  },
};
