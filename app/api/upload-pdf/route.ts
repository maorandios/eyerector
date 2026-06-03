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
      { error: "PDF backend is not configured. Set CHAT_TO_IFC_API_URL." },
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

  try {
    const upstream = await fetch(`${base}/upload-pdf`, { method: "POST", body: outbound });
    const body = await upstream.text();
    if (!upstream.ok) {
      return NextResponse.json(
        { error: body || `Upstream error (${upstream.status})` },
        { status: upstream.status },
      );
    }
    return new NextResponse(body, {
      status: 200,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upstream request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
