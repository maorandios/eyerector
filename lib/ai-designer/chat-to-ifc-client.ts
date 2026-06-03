import type { ChatToIfcRequestBody } from "@/components/ai-designer/types";

const DEFAULT_CHAT_TO_IFC_BASE = "http://localhost:8011";

const RAW_CHAT_TO_IFC_API_URL = process.env.NEXT_PUBLIC_CHAT_TO_IFC_API_URL?.trim();
const USE_DIRECT_PYTHON =
  process.env.NEXT_PUBLIC_CHAT_TO_IFC_DIRECT?.trim().toLowerCase() === "1" ||
  process.env.NEXT_PUBLIC_CHAT_TO_IFC_DIRECT?.trim().toLowerCase() === "true";

function normalizeApiBase(raw: string): string {
  const withProtocol = raw.match(/^https?:\/\//i) ? raw : `http://${raw}`;
  return withProtocol.replace(/\/$/, "");
}

function resolveEndpoint(): string {
  if (USE_DIRECT_PYTHON && RAW_CHAT_TO_IFC_API_URL) {
    return `${normalizeApiBase(RAW_CHAT_TO_IFC_API_URL)}/api/chat-to-ifc`;
  }
  if (typeof window !== "undefined") {
    return `${window.location.origin}/api/chat-to-ifc`;
  }
  if (RAW_CHAT_TO_IFC_API_URL) {
    return `${normalizeApiBase(RAW_CHAT_TO_IFC_API_URL)}/api/chat-to-ifc`;
  }
  return `${DEFAULT_CHAT_TO_IFC_BASE}/api/chat-to-ifc`;
}

export class ChatToIfcError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ChatToIfcError";
    this.status = status;
  }
}

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: string;
      detail?: string;
      message?: string;
    };
    return payload.detail ?? payload.error ?? payload.message ?? response.statusText;
  }
  const text = await response.text().catch(() => "");
  return text.trim() || response.statusText || "Request failed";
}

export type ChatToIfcResult = {
  blob: Blob;
  /** Built profiles summary from backend (X-Eyesteel-Spec header). */
  specSummary?: string;
};

/**
 * POST prompt + history; returns raw IFC bytes as a Blob.
 * Defaults to same-origin Next.js proxy `/api/chat-to-ifc`.
 * Set NEXT_PUBLIC_CHAT_TO_IFC_DIRECT=1 to call Python directly.
 */
export async function fetchChatToIfc(body: ChatToIfcRequestBody): Promise<ChatToIfcResult> {
  const endpoint = resolveEndpoint();
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/octet-stream" },
    body: JSON.stringify({
      prompt: body.prompt,
      history: body.history,
      ...(body.messages?.length ? { messages: body.messages } : {}),
    }),
  });

  if (!response.ok) {
    throw new ChatToIfcError(await readErrorMessage(response), response.status);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = (await response.json().catch(() => ({}))) as { error?: string; detail?: string };
    throw new ChatToIfcError(payload.detail ?? payload.error ?? "Unexpected JSON response");
  }

  const blob = await response.blob();
  if (blob.size === 0) {
    throw new ChatToIfcError("Server returned an empty IFC file");
  }

  const specSummary = response.headers.get("X-Eyesteel-Spec")?.trim() || undefined;
  return { blob, specSummary };
}
