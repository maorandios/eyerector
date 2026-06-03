"use client";

import { cn } from "@/lib/utils";
import type { PageAsset } from "@/lib/plan-crop/types";
import { he } from "@/lib/i18n/he";

type PdfPageGalleryProps = {
  pages: PageAsset[];
  resolveUrl: (path: string) => string;
  selectedPageIndex: number | null;
  onSelect: (pageIndex: number) => void;
};

export function PdfPageGallery({
  pages,
  resolveUrl,
  selectedPageIndex,
  onSelect,
}: PdfPageGalleryProps) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-slate-400">{he.planCropGalleryHint}</p>
      <div className="flex gap-3 overflow-x-auto pb-2 touch-pan-x">
        {pages.map((page) => {
          const selected = selectedPageIndex === page.page_index;
          return (
            <button
              key={page.page_index}
              type="button"
              onClick={() => onSelect(page.page_index)}
              className={cn(
                "flex shrink-0 flex-col items-center gap-1 rounded-lg border p-1 transition",
                selected
                  ? "border-[#00ffcc] ring-2 ring-[#00ffcc]/40"
                  : "border-slate-700 hover:border-slate-500",
              )}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={resolveUrl(page.url)}
                alt={`${he.planCropPageLabel} ${page.page_index}`}
                className="h-28 w-auto max-w-[140px] rounded object-contain bg-white"
              />
              <span className="text-xs text-slate-300">
                {he.planCropPageLabel} {page.page_index}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
