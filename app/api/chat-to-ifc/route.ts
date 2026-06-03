import { NextResponse } from "next/server";
import type { ChatToIfcRequestBody } from "@/components/ai-designer/types";

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
  let body: ChatToIfcRequestBody;
  try {
    body = (await request.json()) as ChatToIfcRequestBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const prompt = typeof body.prompt === "string" ? body.prompt.trim() : "";
  if (!prompt) {
    return NextResponse.json({ error: "prompt is required" }, { status: 400 });
  }

  const messages = Array.isArray(body.messages) ? body.messages : [];

  const base = backendBaseUrl();
  if (!base) {
    return NextResponse.json(
      {
        error:
          "Chat-to-IFC backend is not configured. Set CHAT_TO_IFC_API_URL (or NEXT_PUBLIC_CHAT_TO_IFC_API_URL) to your Python service base URL.",
      },
      { status: 503 },
    );
  }

  const history = Array.isArray(body.history) ? body.history : messages;

  const upstream = `${base}/api/chat-to-ifc`;
  try {
    const upstreamResponse = await fetch(upstream, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/octet-stream",
      },
      body: JSON.stringify({ prompt, history, messages }),
    });

    if (!upstreamResponse.ok) {
      const detail = await upstreamResponse.text().catch(() => upstreamResponse.statusText);
      return NextResponse.json(
        { error: detail || `Upstream error (${upstreamResponse.status})` },
        { status: upstreamResponse.status },
      );
    }

    const ifcBytes = await upstreamResponse.arrayBuffer();
    if (ifcBytes.byteLength === 0) {
      return NextResponse.json({ error: "Upstream returned empty IFC body" }, { status: 502 });
    }

    const specHeader = upstreamResponse.headers.get("X-Eyesteel-Spec");
    const responseHeaders: Record<string, string> = {
      "Content-Type": "application/octet-stream",
      "Content-Disposition": 'attachment; filename="ai-generated.ifc"',
      "Cache-Control": "no-store",
    };
    if (specHeader) {
      responseHeaders["X-Eyesteel-Spec"] = specHeader;
    }

    return new NextResponse(ifcBytes, {
      status: 200,
      headers: responseHeaders,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upstream request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
