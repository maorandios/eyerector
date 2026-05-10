/**
 * Builds a PNG of the 3D canvas with optional markup overlaid — no React UI chrome.
 */
export async function compositeViewerSnapshotPngBlob(
  webglCanvas: HTMLCanvasElement,
  markupCanvas: HTMLCanvasElement | null,
): Promise<Blob | null> {
  const rect = webglCanvas.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;
  if (w <= 0 || h <= 0) return null;

  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  const outW = Math.max(1, Math.round(w * dpr));
  const outH = Math.max(1, Math.round(h * dpr));

  const out = document.createElement("canvas");
  out.width = outW;
  out.height = outH;
  const ctx = out.getContext("2d");
  if (!ctx) return null;

  try {
    ctx.drawImage(webglCanvas, 0, 0, webglCanvas.width, webglCanvas.height, 0, 0, outW, outH);
  } catch {
    return null;
  }

  if (
    markupCanvas &&
    markupCanvas.width > 0 &&
    markupCanvas.height > 0
  ) {
    try {
      ctx.drawImage(
        markupCanvas,
        0,
        0,
        markupCanvas.width,
        markupCanvas.height,
        0,
        0,
        outW,
        outH,
      );
    } catch {
      /* ignore markup layer errors */
    }
  }

  return new Promise((resolve) => {
    out.toBlob((b) => resolve(b ?? null), "image/png");
  });
}

export async function copyImageBlobToClipboard(blob: Blob): Promise<boolean> {
  try {
    if (
      navigator.clipboard &&
      typeof ClipboardItem !== "undefined" &&
      navigator.clipboard.write
    ) {
      await navigator.clipboard.write([
        new ClipboardItem({
          [blob.type]: blob,
        }),
      ]);
      return true;
    }
  } catch {
    /* HTTP / permissions / unsupported */
  }
  return false;
}
