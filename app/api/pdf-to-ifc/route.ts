import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function backendBaseUrl(): string | null {
  const raw =
    process.env.CHAT_TO_IFC_API_URL?.trim() ||
    process.env.NEXT_PUBLIC_CHAT_TO_IFC_API_URL?.trim();
  if (!raw) return null;
  const withProtocol = raw.match(/^https?:\/\//i) ? raw : `https://${raw}`;
  return withProtocol.replace(/\/$/, "");
}

export async function POST(request: Request) {
  const base = backendBaseUrl();
  if (!base) {
    return NextResponse.json(
      {
        error:
          "PDF backend is not configured. Set CHAT_TO_IFC_API_URL or NEXT_PUBLIC_CHAT_TO_IFC_API_URL.",
      },
      { status: 503 },
    );
  }

  const incoming = await request.formData();
  const file = incoming.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "file is required" }, { status: 400 });
  }

  const outbound = new FormData();
  outbound.append("file", file);
  const scaleNote = incoming.get("scale_note");
  const hints = incoming.get("hints");
  if (typeof scaleNote === "string" && scaleNote.trim()) {
    outbound.append("scale_note", scaleNote.trim());
  }
  if (typeof hints === "string" && hints.trim()) {
    outbound.append("hints", hints.trim());
  }

  try {
    const upstream = await fetch(`${base}/api/pdf-to-ifc`, {
      method: "POST",
      body: outbound,
    });

    if (!upstream.ok) {
      const detail = await upstream.text().catch(() => upstream.statusText);
      return NextResponse.json(
        { error: detail || `Upstream error (${upstream.status})` },
        { status: upstream.status },
      );
    }

    const ifcBytes = await upstream.arrayBuffer();
    const headers: Record<string, string> = {
      "Content-Type": "application/octet-stream",
      "Content-Disposition": 'attachment; filename="from-plan.ifc"',
      "Cache-Control": "no-store",
    };
    const spec = upstream.headers.get("X-Eyesteel-Spec");
    const intent = upstream.headers.get("X-Eyesteel-Intent");
    if (spec) headers["X-Eyesteel-Spec"] = spec;
    if (intent) headers["X-Eyesteel-Intent"] = intent;

    return new NextResponse(ifcBytes, { status: 200, headers });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upstream request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
