/**
 * Builds a PNG of the 3D canvas with optional panel and markup overlays.
 */
export async function compositeViewerSnapshotPngBlob(
  webglCanvas: HTMLCanvasElement,
  markupCanvas: HTMLCanvasElement | null,
  overlayElements: readonly HTMLElement[] = [],
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

  for (const el of overlayElements) {
    drawElementOverlay(ctx, el, rect, dpr);
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
    try {
      out.toBlob((b) => resolve(b ?? null), "image/png");
    } catch {
      resolve(null);
    }
  });
}

function drawElementOverlay(
  ctx: CanvasRenderingContext2D,
  root: HTMLElement,
  baseRect: DOMRect,
  dpr: number,
): void {
  const rootRect = root.getBoundingClientRect();
  if (rootRect.width <= 0 || rootRect.height <= 0) return;

  ctx.save();
  ctx.beginPath();
  ctx.rect(
    (rootRect.left - baseRect.left) * dpr,
    (rootRect.top - baseRect.top) * dpr,
    rootRect.width * dpr,
    rootRect.height * dpr,
  );
  ctx.clip();
  drawElementTree(ctx, root, baseRect, dpr);
  ctx.restore();
}

function drawElementTree(
  ctx: CanvasRenderingContext2D,
  node: Element,
  baseRect: DOMRect,
  dpr: number,
): void {
  const style = window.getComputedStyle(node);
  if (style.display === "none" || style.visibility === "hidden") return;

  const rect = node.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return;

  const alpha = Number.parseFloat(style.opacity || "1");
  ctx.save();
  if (Number.isFinite(alpha)) ctx.globalAlpha *= alpha;
  drawElementBox(ctx, style, rect, baseRect, dpr);

  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      drawTextNode(ctx, child as Text, style, baseRect, dpr);
    } else if (child.nodeType === Node.ELEMENT_NODE) {
      const childEl = child as Element;
      if (childEl.tagName.toLowerCase() !== "svg") {
        drawElementTree(ctx, childEl, baseRect, dpr);
      }
    }
  }
  ctx.restore();
}

function drawElementBox(
  ctx: CanvasRenderingContext2D,
  style: CSSStyleDeclaration,
  rect: DOMRect,
  baseRect: DOMRect,
  dpr: number,
): void {
  const x = (rect.left - baseRect.left) * dpr;
  const y = (rect.top - baseRect.top) * dpr;
  const w = rect.width * dpr;
  const h = rect.height * dpr;
  const radius = parseCssPx(style.borderRadius) * dpr;

  if (hasPaint(style.backgroundColor)) {
    ctx.fillStyle = style.backgroundColor;
    roundedRect(ctx, x, y, w, h, radius);
    ctx.fill();
  }

  const borderWidth = parseCssPx(style.borderTopWidth) * dpr;
  if (borderWidth > 0 && hasPaint(style.borderTopColor)) {
    ctx.strokeStyle = style.borderTopColor;
    ctx.lineWidth = borderWidth;
    roundedRect(ctx, x + borderWidth / 2, y + borderWidth / 2, w - borderWidth, h - borderWidth, radius);
    ctx.stroke();
  }
}

function drawTextNode(
  ctx: CanvasRenderingContext2D,
  textNode: Text,
  style: CSSStyleDeclaration,
  baseRect: DOMRect,
  dpr: number,
): void {
  const text = textNode.textContent?.replace(/\s+/g, " ").trim();
  if (!text) return;

  const range = document.createRange();
  range.selectNodeContents(textNode);
  const textRect = range.getBoundingClientRect();
  range.detach();
  if (textRect.width <= 0 || textRect.height <= 0) return;

  const fontSize = parseCssPx(style.fontSize) || 12;
  const fontWeight = style.fontWeight || "400";
  const fontFamily = style.fontFamily || "sans-serif";
  ctx.font = `${fontWeight} ${fontSize * dpr}px ${fontFamily}`;
  ctx.fillStyle = hasPaint(style.color) ? style.color : "#111827";
  ctx.textBaseline = "alphabetic";
  ctx.direction = style.direction === "rtl" ? "rtl" : "ltr";
  ctx.textAlign = style.textAlign === "center" ? "center" : style.direction === "rtl" ? "right" : "left";

  const x =
    ctx.textAlign === "center"
      ? (textRect.left - baseRect.left + textRect.width / 2) * dpr
      : ctx.textAlign === "right"
        ? (textRect.right - baseRect.left) * dpr
        : (textRect.left - baseRect.left) * dpr;
  const y = (textRect.top - baseRect.top + fontSize * 0.88) * dpr;
  ctx.fillText(text, x, y, Math.max(1, textRect.width * dpr));
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function parseCssPx(value: string): number {
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}

function hasPaint(value: string): boolean {
  return Boolean(
    value &&
      value !== "transparent" &&
      value !== "rgba(0, 0, 0, 0)" &&
      value !== "rgba(0,0,0,0)" &&
      !value.endsWith(", 0)"),
  );
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
