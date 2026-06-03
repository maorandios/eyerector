"use client";

import type { RegionCropCalibrationResult } from "@/lib/plan-crop/types";
import type { SnappedColumn } from "@/lib/plan-crop/grid-snap";
import { duplicateCellGroups, stationsAlignedWithLines } from "@/lib/plan-crop/grid-snap";
import { he } from "@/lib/i18n/he";
import { Button } from "@/components/ui/button";

type GridMarkupReviewPanelProps = {
  calibration: RegionCropCalibrationResult;
  snapped: SnappedColumn[];
  clickCount: number;
  isLoading: boolean;
  onBack: () => void;
  onApprove: () => void;
};

export function GridMarkupReviewPanel({
  calibration,
  snapped,
  clickCount,
  isLoading,
  onBack,
  onApprove,
}: GridMarkupReviewPanelProps) {
  const dupes = duplicateCellGroups(snapped);
  const { x_lines_px, y_lines_px, xs_mm, ys_mm } = stationsAlignedWithLines(calibration);
  const mm = calibration.mm_per_px;

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">{he.planCropGridReviewTitle}</h2>
        <p className="text-xs text-slate-400">{he.planCropGridReviewClickGridHint}</p>
      </div>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-400">
        <dt>{he.planCropGridReviewRefLines} X</dt>
        <dd className="text-slate-200">{x_lines_px.length}</dd>
        <dt>{he.planCropGridReviewRefLines} Y</dt>
        <dd className="text-slate-200">{y_lines_px.length}</dd>
        <dt>{he.planCropColumns} ({he.planCropGridReviewMarked})</dt>
        <dd className="text-slate-200">{clickCount}</dd>
        <dt>{he.planCropGridReviewPlaced}</dt>
        <dd className="text-slate-200">{snapped.length}</dd>
        {mm ? (
          <>
            <dt>mm/px</dt>
            <dd className="text-slate-200">{mm.toFixed(2)}</dd>
          </>
        ) : null}
      </dl>

      {dupes.size > 0 ? (
        <div className="rounded border border-red-500/50 bg-red-950/40 p-2 text-xs text-red-300">
          <p className="font-medium">{he.planCropGridReviewDuplicate}</p>
          <ul className="mt-1 list-inside list-disc">
            {[...dupes.entries()].map(([key, list]) => (
              <li key={key}>
                {key}: {list.map((s) => s.mark).join(", ")}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="max-h-48 overflow-y-auto rounded border border-slate-700">
        <table className="w-full text-left text-[11px]">
          <thead className="sticky top-0 bg-slate-900 text-slate-500">
            <tr>
              <th className="px-2 py-1">{he.planCropGridReviewMark}</th>
              <th className="px-2 py-1">{he.planCropGridReviewNearX}</th>
              <th className="px-2 py-1">{he.planCropGridReviewNearY}</th>
              <th className="px-2 py-1">mm X</th>
              <th className="px-2 py-1">mm Y</th>
            </tr>
          </thead>
          <tbody>
            {snapped.map((s) => (
              <tr
                key={s.clickId}
                className={s.duplicateCell ? "bg-red-950/30 text-red-200" : "text-slate-300"}
              >
                <td className="px-2 py-0.5">{s.mark}</td>
                <td className="px-2 py-0.5">{s.grid_index_x + 1}</td>
                <td className="px-2 py-0.5">{String.fromCharCode(65 + s.grid_index_y)}</td>
                <td className="px-2 py-0.5">{Math.round(s.x_mm)}</td>
                <td className="px-2 py-0.5">{Math.round(s.y_mm)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Button type="button" variant="ghost" disabled={isLoading} onClick={onBack}>
        {he.planCropGridReviewBack}
      </Button>
      <Button
        type="button"
        disabled={isLoading || snapped.length === 0}
        onClick={onApprove}
        className="bg-[#00ffcc] text-slate-950 hover:bg-[#00e6b8]"
      >
        {he.planCropGridReviewApprove}
      </Button>
    </div>
  );
}
