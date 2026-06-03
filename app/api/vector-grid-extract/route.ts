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

  const body = await request.text();
  try {
    const upstream = await fetch(`${base}/api/vector-grid-extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const text = await upstream.text();
    if (!upstream.ok) {
      return NextResponse.json(
        { error: text || `Upstream error (${upstream.status})` },
        { status: upstream.status },
      );
    }
    return new NextResponse(text, {
      status: 200,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upstream request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
