"use client";

import { Search, Layers3, RotateCcw, ScanSearch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { he } from "@/lib/i18n/he";

interface Props {
  onSearch: () => void;
  onLayers: () => void;
  onResetView: () => void;
  onFitAll: () => void;
}

export function FloatingActions({
  onSearch,
  onLayers,
  onResetView,
  onFitAll,
}: Props) {
  return (
    <div className="absolute bottom-24 left-3 z-20 flex flex-col gap-2">
      <Button size="icon" variant="secondary" onClick={onSearch} aria-label={he.search}>
        <Search size={20} />
      </Button>
      <Button size="icon" variant="secondary" onClick={onLayers} aria-label={he.layers}>
        <Layers3 size={20} />
      </Button>
      <Button size="icon" variant="secondary" onClick={onResetView} aria-label={he.resetView}>
        <RotateCcw size={20} />
      </Button>
      <Button size="icon" variant="secondary" onClick={onFitAll} aria-label={he.fitAll}>
        <ScanSearch size={20} />
      </Button>
    </div>
  );
}
