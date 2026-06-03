const DEFAULT_API_BASE = "http://localhost:8011";

const RAW_API_URL = process.env.NEXT_PUBLIC_CHAT_TO_IFC_API_URL?.trim();
const USE_DIRECT_PYTHON =
  process.env.NEXT_PUBLIC_CHAT_TO_IFC_DIRECT?.trim().toLowerCase() === "1" ||
  process.env.NEXT_PUBLIC_CHAT_TO_IFC_DIRECT?.trim().toLowerCase() === "true";

function normalizeApiBase(raw: string): string {
  const withProtocol = raw.match(/^https?:\/\//i) ? raw : `http://${raw}`;
  return withProtocol.replace(/\/$/, "");
}

function resolveApiBase(): string {
  if (RAW_API_URL) {
    return normalizeApiBase(RAW_API_URL);
  }
  return DEFAULT_API_BASE;
}

function resolvePdfToIfcEndpoint(): string {
  if (USE_DIRECT_PYTHON && RAW_API_URL) {
    return `${resolveApiBase()}/api/pdf-to-ifc`;
  }
  if (typeof window !== "undefined") {
    return `${window.location.origin}/api/pdf-to-ifc`;
  }
  return `${resolveApiBase()}/api/pdf-to-ifc`;
}

function resolvePdfToJsonEndpoint(): string {
  if (USE_DIRECT_PYTHON && RAW_API_URL) {
    return `${resolveApiBase()}/api/pdf-to-structural-json`;
  }
  if (typeof window !== "undefined") {
    return `${window.location.origin}/api/pdf-to-structural-json`;
  }
  return `${resolveApiBase()}/api/pdf-to-structural-json`;
}

export class PdfPlanError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "PdfPlanError";
    this.status = status;
  }
}

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: string;
      detail?: string | { message?: string; errors?: string[] };
      message?: string;
    };
    if (typeof payload.detail === "object" && payload.detail !== null) {
      const d = payload.detail as { message?: string; errors?: string[] };
      if (d.errors?.length) {
        return `${d.message ?? "Validation failed"}: ${d.errors.join("; ")}`;
      }
      return d.message ?? JSON.stringify(payload.detail);
    }
    return String(payload.detail ?? payload.error ?? payload.message ?? response.statusText);
  }
  const text = await response.text().catch(() => "");
  return text.trim() || response.statusText || "Request failed";
}

export type PdfToIfcResult = {
  blob: Blob;
  specSummary?: string;
  intentSummary?: string;
};

export type PdfIngestReport = {
  page_count: number;
  likely_vector: boolean;
  text_char_count: number;
  drawing_op_count: number;
  text_excerpt: string;
  warnings: string[];
};

export type PdfToJsonResult = {
  status: string;
  message: string;
  extraction_method: string;
  ai_model?: string | null;
  warnings: string[];
  ingest: PdfIngestReport;
  model: unknown | null;
  validation: {
    ok: boolean;
    errors: string[];
    element_count: number;
    slab_count?: number;
  } | null;
};

export async function fetchPdfToIfc(
  file: File,
  options?: { scaleNote?: string; hints?: string },
): Promise<PdfToIfcResult> {
  const form = new FormData();
  form.append("file", file);
  if (options?.scaleNote?.trim()) {
    form.append("scale_note", options.scaleNote.trim());
  }
  if (options?.hints?.trim()) {
    form.append("hints", options.hints.trim());
  }

  const response = await fetch(resolvePdfToIfcEndpoint(), {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    throw new PdfPlanError(await readErrorMessage(response), response.status);
  }

  const blob = await response.blob();
  if (blob.size === 0) {
    throw new PdfPlanError("Server returned an empty IFC file");
  }

  return {
    blob,
    specSummary: response.headers.get("X-Eyesteel-Spec")?.trim() || undefined,
    intentSummary: response.headers.get("X-Eyesteel-Intent")?.trim() || undefined,
  };
}

export async function fetchPdfToStructuralJson(
  file: File,
  options?: { scaleNote?: string; hints?: string },
): Promise<PdfToJsonResult> {
  const form = new FormData();
  form.append("file", file);
  if (options?.scaleNote?.trim()) {
    form.append("scale_note", options.scaleNote.trim());
  }
  if (options?.hints?.trim()) {
    form.append("hints", options.hints.trim());
  }

  const response = await fetch(resolvePdfToJsonEndpoint(), {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    throw new PdfPlanError(await readErrorMessage(response), response.status);
  }

  return (await response.json()) as PdfToJsonResult;
}
