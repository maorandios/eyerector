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
      { error: "PDF backend is not configured." },
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
    const upstream = await fetch(`${base}/api/pdf-to-structural-json`, {
      method: "POST",
      body: outbound,
    });
    const payload = await upstream.json().catch(() => ({}));
    return NextResponse.json(payload, { status: upstream.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upstream request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
