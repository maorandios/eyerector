"use client";

import { useCallback, useState } from "react";
import { ViewerCanvas } from "@/components/viewer/ViewerCanvas";
import { AiViewportPlaceholder } from "./AiViewportPlaceholder";
import type { ViewerEngine } from "@/lib/viewer/engine";
import { cn } from "@/lib/utils";

interface AiDesignerViewportProps {
  hasModel: boolean;
  className?: string;
  placeholderMessage?: string;
  onEngineReady: (engine: ViewerEngine | null) => void;
}

export function AiDesignerViewport({
  hasModel,
  className,
  placeholderMessage,
  onEngineReady,
}: AiDesignerViewportProps) {
  const [engineReady, setEngineReady] = useState(false);

  const handleReady = useCallback(
    (engine: ViewerEngine | null) => {
      setEngineReady(!!engine);
      onEngineReady(engine);
    },
    [onEngineReady],
  );

  const showPlaceholder = !hasModel;

  return (
    <div className={cn("relative h-full w-full", className)}>
      <ViewerCanvas onReady={handleReady} />
      {showPlaceholder && (
        <div
          className={cn(
            "pointer-events-none absolute inset-0 z-[1]",
            engineReady ? "opacity-100" : "opacity-0",
          )}
          aria-hidden={!showPlaceholder}
        >
          <AiViewportPlaceholder className="h-full" message={placeholderMessage} />
        </div>
      )}
    </div>
  );
}
