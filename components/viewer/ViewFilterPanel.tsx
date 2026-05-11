"use client";

import { Fragment, useMemo, useState } from "react";
import { ChevronDown, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AnalyzerAssembly, AnalyzerPart } from "@/types/domain";
import {
  aggregateAssembliesByMark,
  type AggregatedAssemblyRow,
} from "@/lib/viewer/modelAggregates";
import {
  type ViewFilterGhostTab,
  useViewFilterStore,
} from "@/lib/state/view-filter-store";
import { formatCount, formatQuantityInt } from "@/lib/format-numbers";
import {
  aggregateProfilesForModelTab,
  aggregateSteelPartsForModelTab,
  displayPartMark,
  steelPartEntityQtyContribution,
} from "@/components/viewer/SelectionPickDetails";
import { cn } from "@/lib/utils";

type FilterTab = ViewFilterGhostTab;

function aggregatePartsForAssemblyRow(row: AggregatedAssemblyRow): { part: AnalyzerPart; qty: number }[] {
  const m = new Map<string, { part: AnalyzerPart; qty: number }>();
  for (const asm of row.instances) {
    for (const p of asm.parts) {
      const add = p.quantity ?? 1;
      const prev = m.get(p.id);
      if (prev) prev.qty += add;
      else m.set(p.id, { part: p, qty: add });
    }
  }
  return Array.from(m.values()).sort((a, b) =>
    displayPartMark(a.part).localeCompare(displayPartMark(b.part), "he", { numeric: true }),
  );
}

function TabGhostEye({
  label,
  active,
  ghostOnThisTab,
  onSelectTab,
  onToggleGhost,
}: {
  label: string;
  active: boolean;
  ghostOnThisTab: boolean;
  onSelectTab: () => void;
  onToggleGhost: () => void;
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-1 items-stretch rounded-md border border-transparent",
        active ? "border-zinc-600 bg-zinc-700 text-zinc-100" : "text-zinc-400",
      )}
    >
      <button
        type="button"
        className={cn(
          "min-w-0 flex-1 truncate rounded-l-md px-1 py-2 text-xs font-medium transition-colors",
          !active && "hover:bg-zinc-800/80",
        )}
        onClick={onSelectTab}
      >
        {label}
      </button>
      <button
        type="button"
        className={cn(
          "shrink-0 rounded-r-md border-r border-zinc-600 px-1 transition-colors hover:bg-zinc-600/50",
          ghostOnThisTab ? "bg-emerald-900/70 text-emerald-200" : "text-zinc-500 hover:text-zinc-200",
        )}
        title="מצב רוח (כמו הצג בהקשר): לחץ שורות בטבלה כדי להציג רגיל"
        aria-label={`מצב רוח בשונית ${label}`}
        aria-pressed={ghostOnThisTab}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onToggleGhost();
        }}
      >
        <Eye className="mx-auto h-4 w-4" />
      </button>
    </div>
  );
}

type Props = {
  assemblies: AnalyzerAssembly[];
  steelParts: AnalyzerPart[];
  onClose: () => void;
};

export function ViewFilterPanel({ assemblies, steelParts, onClose }: Props) {
  const [tab, setTab] = useState<FilterTab>("assemblies");
  const [expandedAssemblyKey, setExpandedAssemblyKey] = useState<string | null>(null);
  const [expandedPartRowKey, setExpandedPartRowKey] = useState<string | null>(null);
  const [expandedProfileRowKey, setExpandedProfileRowKey] = useState<string | null>(null);

  const toggleAssemblyKey = useViewFilterStore((s) => s.toggleAssemblyKey);
  const togglePartId = useViewFilterStore((s) => s.togglePartId);
  const togglePartTabGroupKey = useViewFilterStore((s) => s.togglePartTabGroupKey);
  const toggleProfileTabGroupKey = useViewFilterStore((s) => s.toggleProfileTabGroupKey);
  const isAssemblyHidden = useViewFilterStore((s) => s.isAssemblyHidden);
  const isPartHidden = useViewFilterStore((s) => s.isPartHidden);
  const isPartTabGroupHidden = useViewFilterStore((s) => s.isPartTabGroupHidden);
  const isProfileTabGroupHidden = useViewFilterStore((s) => s.isProfileTabGroupHidden);
  const reset = useViewFilterStore((s) => s.reset);
  const ghostFocusTab = useViewFilterStore((s) => s.ghostFocusTab);
  const ghostRevealedPartIds = useViewFilterStore((s) => s.ghostRevealedPartIds);
  const activateGhostRevealTab = useViewFilterStore((s) => s.activateGhostRevealTab);
  const exitGhostRevealMode = useViewFilterStore((s) => s.exitGhostRevealMode);
  const toggleGhostRevealGroup = useViewFilterStore((s) => s.toggleGhostRevealGroup);

  const ghostRevealActive = ghostFocusTab !== null;

  const rows = useMemo(() => aggregateAssembliesByMark(assemblies), [assemblies]);
  const modelPartRows = useMemo(() => aggregateSteelPartsForModelTab(steelParts), [steelParts]);
  const modelProfileRows = useMemo(() => aggregateProfilesForModelTab(steelParts), [steelParts]);

  const handleReset = () => {
    reset();
  };

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-100">סינון תצוגה</p>
        <div className="flex items-center gap-2">
          <Button type="button" variant="secondary" className="h-8 px-3 text-xs font-semibold" onClick={handleReset}>
            איפוס
          </Button>
          <Button type="button" variant="ghost" className="h-8 px-2 text-xs" onClick={onClose}>
            סגור
          </Button>
        </div>
      </div>

      <div className="mb-2 flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900/60 p-1">
        <TabGhostEye
          label="הרכבות"
          active={tab === "assemblies"}
          ghostOnThisTab={ghostFocusTab === "assemblies"}
          onSelectTab={() => setTab("assemblies")}
          onToggleGhost={() => {
            if (ghostFocusTab === "assemblies") exitGhostRevealMode();
            else activateGhostRevealTab("assemblies");
          }}
        />
        <TabGhostEye
          label="חלקים"
          active={tab === "parts"}
          ghostOnThisTab={ghostFocusTab === "parts"}
          onSelectTab={() => setTab("parts")}
          onToggleGhost={() => {
            if (ghostFocusTab === "parts") exitGhostRevealMode();
            else activateGhostRevealTab("parts");
          }}
        />
        <TabGhostEye
          label="פרופילים"
          active={tab === "profiles"}
          ghostOnThisTab={ghostFocusTab === "profiles"}
          onSelectTab={() => setTab("profiles")}
          onToggleGhost={() => {
            if (ghostFocusTab === "profiles") exitGhostRevealMode();
            else activateGhostRevealTab("profiles");
          }}
        />
      </div>

      <div className="max-h-[calc(100vh-12rem)] overflow-auto rounded-xl border border-zinc-800 bg-zinc-950/30 p-2">
        {tab === "assemblies" && (
          <>
            {rows.length === 0 ? (
              <p className="px-1 py-4 text-center text-sm text-zinc-500">אין הרכבות במודל</p>
            ) : (
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-zinc-900 text-zinc-400">
                  <tr>
                    <th className="w-8 p-1" aria-hidden />
                    <th className="p-2 text-right font-medium">מספר הרכבה</th>
                    <th className="p-2 text-right font-medium">כמות</th>
                    <th className="w-11 p-1 text-center font-medium">תצוגה</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const expanded = expandedAssemblyKey === row.key;
                    const asmH = isAssemblyHidden(row.key);
                    const partRows = aggregatePartsForAssemblyRow(row);
                    const assemblyPartIds = partRows.map((pr) => pr.part.id);
                    const assemblyGhostAllRevealed =
                      ghostRevealActive &&
                      assemblyPartIds.length > 0 &&
                      assemblyPartIds.every((id) => ghostRevealedPartIds[id]);

                    return (
                      <Fragment key={row.key}>
                        <tr
                          className="cursor-pointer border-t border-zinc-800 hover:bg-zinc-800/90"
                          onClick={() =>
                            setExpandedAssemblyKey((k) => (k === row.key ? null : row.key))
                          }
                        >
                          <td className="p-1 align-middle">
                            <ChevronDown
                              className={cn(
                                "mx-auto h-4 w-4 text-zinc-500 transition-transform",
                                expanded ? "rotate-180" : "rotate-0",
                              )}
                              aria-hidden
                            />
                          </td>
                          <td className="p-2 font-medium text-zinc-100">{row.displayMark}</td>
                          <td className="p-2 text-zinc-300">{formatCount(row.qty)}</td>
                          <td className="p-1 text-center align-middle">
                            <button
                              type="button"
                              className="inline-flex rounded-md p-1.5 text-zinc-200 hover:bg-zinc-700"
                              title={
                                ghostRevealActive
                                  ? assemblyGhostAllRevealed
                                    ? "החזר קבוצה למצב רוח"
                                    : "הצג חלקי הרכבה רגילים"
                                  : asmH
                                    ? "הצג במודל"
                                    : "הסתר במודל"
                              }
                              aria-label="תצוגה"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (ghostRevealActive) {
                                  toggleGhostRevealGroup(assemblyPartIds);
                                } else {
                                  toggleAssemblyKey(row.key);
                                }
                              }}
                            >
                              {ghostRevealActive ? (
                                assemblyGhostAllRevealed ? (
                                  <Eye className="h-4 w-4" />
                                ) : (
                                  <EyeOff className="h-4 w-4" />
                                )
                              ) : asmH ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </button>
                          </td>
                        </tr>
                        {expanded && (
                          <tr className="border-t border-zinc-800 bg-zinc-900/50">
                            <td colSpan={4} className="p-0">
                              {partRows.length === 0 ? (
                                <p className="px-4 py-3 text-[11px] text-zinc-500">אין חלקים במסכת הרכבה זו</p>
                              ) : (
                                <table className="w-full text-[11px]">
                                  <thead className="text-zinc-500">
                                    <tr>
                                      <th className="p-2 pr-6 text-right font-medium">שם חלק</th>
                                      <th className="p-2 text-right font-medium">כמות</th>
                                      <th className="w-11 p-1 text-center font-medium">תצוגה</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {partRows.map(({ part, qty }: { part: AnalyzerPart; qty: number }) => {
                                      const parentHides = asmH;
                                      const partOnly = !parentHides && isPartHidden(part.id);
                                      const showOff = parentHides || partOnly;
                                      const ghostRev = ghostRevealedPartIds[part.id];

                                      return (
                                        <tr key={part.id} className="border-t border-zinc-800/80">
                                          <td className="p-2 pr-6 font-medium text-zinc-200">{displayPartMark(part)}</td>
                                          <td className="p-2 text-zinc-400">{formatQuantityInt(qty)}</td>
                                          <td className="p-1 text-center">
                                            <button
                                              type="button"
                                              className={cn(
                                                "inline-flex rounded-md p-1.5",
                                                parentHides && !ghostRevealActive
                                                  ? "cursor-not-allowed text-zinc-600"
                                                  : "text-zinc-200 hover:bg-zinc-700",
                                              )}
                                              disabled={parentHides && !ghostRevealActive}
                                              title={
                                                ghostRevealActive
                                                  ? ghostRev
                                                    ? "החזר למצב רוח"
                                                    : "הצג חלק רגיל"
                                                  : parentHides
                                                    ? "הרכבה מוסתרת"
                                                    : partOnly
                                                      ? "הצג במודל"
                                                      : "הסתר במודל"
                                              }
                                              aria-label="תצוגת חלק"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                if (ghostRevealActive) {
                                                  toggleGhostRevealGroup([part.id]);
                                                  return;
                                                }
                                                if (!parentHides) togglePartId(part.id);
                                              }}
                                            >
                                              {ghostRevealActive ? (
                                                ghostRev ? (
                                                  <Eye className="h-3.5 w-3.5" />
                                                ) : (
                                                  <EyeOff className="h-3.5 w-3.5" />
                                                )
                                              ) : showOff ? (
                                                <EyeOff className="h-3.5 w-3.5" />
                                              ) : (
                                                <Eye className="h-3.5 w-3.5" />
                                              )}
                                            </button>
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        )}

        {tab === "parts" && (
          <>
            {modelPartRows.length === 0 ? (
              <p className="px-1 py-4 text-center text-sm text-zinc-500">אין חלקים במודל</p>
            ) : (
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-zinc-900 text-zinc-400">
                  <tr>
                    <th className="w-8 p-1" aria-hidden />
                    <th className="p-2 text-right font-medium">מספר חלק</th>
                    <th className="p-2 text-right font-medium">פרופיל</th>
                    <th className="p-2 text-right font-medium">כמות</th>
                    <th className="w-11 p-1 text-center font-medium">תצוגה</th>
                  </tr>
                </thead>
                <tbody>
                  {modelPartRows.map((row) => {
                    const canExpand = row.effectiveQty > 1 || row.instances.length > 1;
                    const expanded = expandedPartRowKey === row.key;
                    const groupH = isPartTabGroupHidden(row.key);
                    const rowPartIds = row.instances.map((p) => p.id);
                    const partGroupGhostAllRevealed =
                      ghostRevealActive &&
                      rowPartIds.length > 0 &&
                      rowPartIds.every((id) => ghostRevealedPartIds[id]);

                    return (
                      <Fragment key={row.key}>
                        <tr
                          className={cn(
                            "border-t border-zinc-800 hover:bg-zinc-800/90",
                            canExpand ? "cursor-pointer" : "",
                          )}
                          onClick={() => {
                            if (!canExpand) return;
                            setExpandedPartRowKey((k) => (k === row.key ? null : row.key));
                          }}
                        >
                          <td className="p-1 align-middle">
                            {canExpand ? (
                              <ChevronDown
                                className={cn(
                                  "mx-auto h-4 w-4 text-zinc-500 transition-transform",
                                  expanded ? "rotate-180" : "rotate-0",
                                )}
                                aria-hidden
                              />
                            ) : (
                              <span className="block h-4 w-4" aria-hidden />
                            )}
                          </td>
                          <td className="p-2 font-medium text-zinc-100">{row.displayMark}</td>
                          <td className="p-2 text-zinc-300">{row.displayProfile}</td>
                          <td className="p-2 text-zinc-300">{formatQuantityInt(row.effectiveQty)}</td>
                          <td className="p-1 text-center align-middle">
                            <button
                              type="button"
                              className="inline-flex rounded-md p-1.5 text-zinc-200 hover:bg-zinc-700"
                              title={
                                ghostRevealActive
                                  ? partGroupGhostAllRevealed
                                    ? "החזר קבוצה למצב רוח"
                                    : "הצג קבוצת חלקים רגילים"
                                  : groupH
                                    ? "הצג במודל"
                                    : "הסתר במודל"
                              }
                              aria-label="תצוגה"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (ghostRevealActive) toggleGhostRevealGroup(rowPartIds);
                                else togglePartTabGroupKey(row.key);
                              }}
                            >
                              {ghostRevealActive ? (
                                partGroupGhostAllRevealed ? (
                                  <Eye className="h-4 w-4" />
                                ) : (
                                  <EyeOff className="h-4 w-4" />
                                )
                              ) : groupH ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </button>
                          </td>
                        </tr>
                        {expanded && canExpand && (
                          <tr className="border-t border-zinc-800 bg-zinc-900/50">
                            <td colSpan={5} className="p-0">
                              <table className="w-full text-[11px]">
                                <thead className="text-zinc-500">
                                  <tr>
                                    <th className="p-2 pr-6 text-right font-medium">מספר חלק</th>
                                    <th className="p-2 text-right font-medium">פרופיל</th>
                                    <th className="p-2 text-right font-medium">כמות</th>
                                    <th className="w-11 p-1 text-center font-medium">תצוגה</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {row.instances.map((part) => {
                                    const parentHides = groupH;
                                    const partOnly = !parentHides && isPartHidden(part.id);
                                    const showOff = parentHides || partOnly;
                                    const ghostRev = ghostRevealedPartIds[part.id];
                                    const subLabel =
                                      displayPartMark(part) +
                                      (part.expressId != null ? ` #${part.expressId}` : "");

                                    return (
                                      <tr key={part.id} className="border-t border-zinc-800/80">
                                        <td
                                          className="p-2 pr-6 font-medium text-zinc-200"
                                          title={part.id}
                                        >
                                          {subLabel}
                                        </td>
                                        <td className="p-2 text-zinc-400">{row.displayProfile}</td>
                                        <td className="p-2 text-zinc-400">
                                          {formatQuantityInt(steelPartEntityQtyContribution(part))}
                                        </td>
                                        <td className="p-1 text-center">
                                          <button
                                            type="button"
                                            className={cn(
                                              "inline-flex rounded-md p-1.5",
                                              parentHides && !ghostRevealActive
                                                ? "cursor-not-allowed text-zinc-600"
                                                : "text-zinc-200 hover:bg-zinc-700",
                                            )}
                                            disabled={parentHides && !ghostRevealActive}
                                            title={
                                              ghostRevealActive
                                                ? ghostRev
                                                  ? "החזר למצב רוח"
                                                  : "הצג חלק רגיל"
                                                : parentHides
                                                  ? "הקבוצה מוסתרת"
                                                  : partOnly
                                                    ? "הצג במודל"
                                                    : "הסתר במודל"
                                            }
                                            aria-label="תצוגת חלק"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              if (ghostRevealActive) {
                                                toggleGhostRevealGroup([part.id]);
                                                return;
                                              }
                                              if (!parentHides) togglePartId(part.id);
                                            }}
                                          >
                                            {ghostRevealActive ? (
                                              ghostRev ? (
                                                <Eye className="h-3.5 w-3.5" />
                                              ) : (
                                                <EyeOff className="h-3.5 w-3.5" />
                                              )
                                            ) : showOff ? (
                                              <EyeOff className="h-3.5 w-3.5" />
                                            ) : (
                                              <Eye className="h-3.5 w-3.5" />
                                            )}
                                          </button>
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        )}

        {tab === "profiles" && (
          <>
            {modelProfileRows.length === 0 ? (
              <p className="px-1 py-4 text-center text-sm text-zinc-500">אין פרופילים במודל</p>
            ) : (
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-zinc-900 text-zinc-400">
                  <tr>
                    <th className="w-8 p-1" aria-hidden />
                    <th className="p-2 text-right font-medium">שם הפרופיל</th>
                    <th className="p-2 text-right font-medium">כמות</th>
                    <th className="w-11 p-1 text-center font-medium">תצוגה</th>
                  </tr>
                </thead>
                <tbody>
                  {modelProfileRows.map((row) => {
                    const canExpand = row.totalQty > 1 || row.instances.length > 1;
                    const expanded = expandedProfileRowKey === row.key;
                    const groupH = isProfileTabGroupHidden(row.key);
                    const profPartIds = row.instances.map((p) => p.id);
                    const profGroupGhostAllRevealed =
                      ghostRevealActive &&
                      profPartIds.length > 0 &&
                      profPartIds.every((id) => ghostRevealedPartIds[id]);

                    return (
                      <Fragment key={row.key}>
                        <tr
                          className={cn(
                            "border-t border-zinc-800 hover:bg-zinc-800/90",
                            canExpand ? "cursor-pointer" : "",
                          )}
                          onClick={() => {
                            if (!canExpand) return;
                            setExpandedProfileRowKey((k) => (k === row.key ? null : row.key));
                          }}
                        >
                          <td className="p-1 align-middle">
                            {canExpand ? (
                              <ChevronDown
                                className={cn(
                                  "mx-auto h-4 w-4 text-zinc-500 transition-transform",
                                  expanded ? "rotate-180" : "rotate-0",
                                )}
                                aria-hidden
                              />
                            ) : (
                              <span className="block h-4 w-4" aria-hidden />
                            )}
                          </td>
                          <td className="p-2 font-medium text-zinc-100">{row.profileLabel}</td>
                          <td className="p-2 text-zinc-300">{formatQuantityInt(row.totalQty)}</td>
                          <td className="p-1 text-center align-middle">
                            <button
                              type="button"
                              className="inline-flex rounded-md p-1.5 text-zinc-200 hover:bg-zinc-700"
                              title={
                                ghostRevealActive
                                  ? profGroupGhostAllRevealed
                                    ? "החזר קבוצה למצב רוח"
                                    : "הצג חלקים רגילים"
                                  : groupH
                                    ? "הצג במודל"
                                    : "הסתר במודל"
                              }
                              aria-label="תצוגה"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (ghostRevealActive) toggleGhostRevealGroup(profPartIds);
                                else toggleProfileTabGroupKey(row.key);
                              }}
                            >
                              {ghostRevealActive ? (
                                profGroupGhostAllRevealed ? (
                                  <Eye className="h-4 w-4" />
                                ) : (
                                  <EyeOff className="h-4 w-4" />
                                )
                              ) : groupH ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </button>
                          </td>
                        </tr>
                        {expanded && canExpand && (
                          <tr className="border-t border-zinc-800 bg-zinc-900/50">
                            <td colSpan={4} className="p-0">
                              <table className="w-full text-[11px]">
                                <thead className="text-zinc-500">
                                  <tr>
                                    <th className="p-2 pr-6 text-right font-medium">מספר חלק</th>
                                    <th className="p-2 text-right font-medium">כמות</th>
                                    <th className="w-11 p-1 text-center font-medium">תצוגה</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {row.instances.map((part) => {
                                    const parentHides = groupH;
                                    const partOnly = !parentHides && isPartHidden(part.id);
                                    const showOff = parentHides || partOnly;
                                    const ghostRev = ghostRevealedPartIds[part.id];
                                    const subLabel =
                                      displayPartMark(part) +
                                      (part.expressId != null ? ` #${part.expressId}` : "");

                                    return (
                                      <tr key={part.id} className="border-t border-zinc-800/80">
                                        <td
                                          className="p-2 pr-6 font-medium text-zinc-200"
                                          title={part.id}
                                        >
                                          {subLabel}
                                        </td>
                                        <td className="p-2 text-zinc-400">
                                          {formatQuantityInt(steelPartEntityQtyContribution(part))}
                                        </td>
                                        <td className="p-1 text-center">
                                          <button
                                            type="button"
                                            className={cn(
                                              "inline-flex rounded-md p-1.5",
                                              parentHides && !ghostRevealActive
                                                ? "cursor-not-allowed text-zinc-600"
                                                : "text-zinc-200 hover:bg-zinc-700",
                                            )}
                                            disabled={parentHides && !ghostRevealActive}
                                            title={
                                              ghostRevealActive
                                                ? ghostRev
                                                  ? "החזר למצב רוח"
                                                  : "הצג חלק רגיל"
                                                : parentHides
                                                  ? "הקבוצה מוסתרת"
                                                  : partOnly
                                                    ? "הצג במודל"
                                                    : "הסתר במודל"
                                            }
                                            aria-label="תצוגת חלק"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              if (ghostRevealActive) {
                                                toggleGhostRevealGroup([part.id]);
                                                return;
                                              }
                                              if (!parentHides) togglePartId(part.id);
                                            }}
                                          >
                                            {ghostRevealActive ? (
                                              ghostRev ? (
                                                <Eye className="h-3.5 w-3.5" />
                                              ) : (
                                                <EyeOff className="h-3.5 w-3.5" />
                                              )
                                            ) : showOff ? (
                                              <EyeOff className="h-3.5 w-3.5" />
                                            ) : (
                                              <Eye className="h-3.5 w-3.5" />
                                            )}
                                          </button>
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </>
  );
}
