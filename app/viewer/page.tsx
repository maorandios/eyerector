"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ViewerCanvas } from "@/components/viewer/ViewerCanvas";
import { TopBar } from "@/components/viewer/TopBar";
import { BottomModeNav } from "@/components/viewer/BottomModeNav";
import { FloatingActions } from "@/components/viewer/actions/FloatingActions";
import { BottomSheet } from "@/components/sheets/BottomSheet";
import { ManagementPanel } from "@/components/modes/management/ManagementPanel";
import { ProductionPanel } from "@/components/modes/production/ProductionPanel";
import { InstallationPanel } from "@/components/modes/installation/InstallationPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { modeConfig } from "@/lib/modes/config";
import { useAppStore } from "@/lib/state/app-store";
import { ViewerEngine } from "@/lib/viewer/engine";
import { he } from "@/lib/i18n/he";

export default function ViewerPage() {
  const router = useRouter();
  const [engine, setEngine] = useState<ViewerEngine | null>(null);
  const {
    file,
    mode,
    setMode,
    selectedElement,
    search,
    setSearch,
    activeSheet,
    setActiveSheet,
    categoryVisibility,
    toggleCategory,
    setLoadingState,
    loadingState,
    transparencyEnabled,
    setTransparencyEnabled,
  } = useAppStore();

  useEffect(() => {
    if (!file) router.replace("/");
  }, [file, router]);

  useEffect(() => {
    if (!engine || !file) return;
    setLoadingState("parsing");
    engine
      .loadFile(file)
      .then(() => setLoadingState("ready"))
      .catch((err) => {
        console.error("IFC load failed:", err);
        setLoadingState("error");
      });
  }, [engine, file, setLoadingState]);

  useEffect(() => {
    if (!engine) return;
    engine.setMode(mode);
  }, [engine, mode]);

  useEffect(() => {
    if (!engine) return;
    Object.entries(categoryVisibility).forEach(([cat, visible]) => {
      engine.setCategoryVisible(cat, visible);
    });
  }, [engine, categoryVisibility]);

  useEffect(() => {
    if (!engine) return;
    engine.setTransparency(transparencyEnabled);
  }, [engine, transparencyEnabled]);

  const onReady = useCallback((instance: ViewerEngine | null) => setEngine(instance), []);
  const modeLabel = modeConfig[mode].label;

  const modePanel = useMemo(() => {
    if (mode === "management") return <ManagementPanel element={selectedElement} />;
    if (mode === "production") return <ProductionPanel assembly={null} />;
    return <InstallationPanel />;
  }, [mode, selectedElement]);

  return (
    <main className="relative h-screen w-screen overflow-hidden">
      <ViewerCanvas onReady={onReady} />
      <TopBar modeLabel={modeLabel} />
      <div className="absolute right-3 top-10 z-20 text-xs text-red-300">
        {loadingState === "error" ? "שגיאה בטעינת IFC" : ""}
      </div>

      <div className="absolute right-3 top-20 z-20">
        <Button variant="secondary" onClick={() => router.push("/")}>
          {he.backToUpload}
        </Button>
      </div>

      <FloatingActions
        onSearch={() => setActiveSheet("search")}
        onLayers={() => setActiveSheet("layers")}
        onResetView={() => engine?.resetView()}
        onFitAll={() => engine?.fitAll()}
      />
      <BottomModeNav mode={mode} onModeChange={setMode} />

      <BottomSheet open={activeSheet !== "none"} title="כלים">
        {activeSheet === "search" && (
          <div className="space-y-3">
            <Input
              placeholder="חפש Assembly / Part / Element"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Button className="w-full" onClick={() => setActiveSheet("none")}>
              סגור
            </Button>
          </div>
        )}
        {activeSheet === "layers" && (
          <div className="grid grid-cols-2 gap-2">
            {Object.keys(categoryVisibility).map((cat) => (
              <Button key={cat} variant="secondary" onClick={() => toggleCategory(cat)}>
                {cat}
              </Button>
            ))}
            <Button
              className="col-span-2"
              onClick={() => setTransparencyEnabled(!transparencyEnabled)}
            >
              {transparencyEnabled ? "בטל שקיפות" : "מצב שקיפות"}
            </Button>
          </div>
        )}
        {modePanel}
      </BottomSheet>
    </main>
  );
}
