import { NextRequest, NextResponse } from "next/server";
import { Mistral } from "@mistralai/mistralai";
import { LiteParse } from "@llamaindex/liteparse";

// ─── Constants ────────────────────────────────────────────────────────────────
const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB
const MAX_PDF_PAGES = 5;
const MAX_IMAGES_PER_REQUEST = 5;

// ─── Mistral client (lazy – only instantiated when needed) ────────────────────
let _mistral: Mistral | null = null;
function getMistralClient(): Mistral {
  if (!_mistral) {
    const apiKey = process.env.MISTRAL_API_KEY;
    if (!apiKey) throw new Error("MISTRAL_API_KEY is not set in environment variables.");
    _mistral = new Mistral({ apiKey });
  }
  return _mistral;
}

// ─── MIME helpers ─────────────────────────────────────────────────────────────
const IMAGE_MIME_TYPES = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/webp",
  "image/avif",
  "image/gif",
  "image/tiff",
  "image/bmp",
]);

const PDF_MIME_TYPE = "application/pdf";

/** Extension → MIME fallback when browser sends empty type */
const EXT_TO_MIME: Record<string, string> = {
  pdf: "application/pdf",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  avif: "image/avif",
  gif: "image/gif",
  tiff: "image/tiff",
  bmp: "image/bmp",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  doc: "application/msword",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  xls: "application/vnd.ms-excel",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ppt: "application/vnd.ms-powerpoint",
  txt: "text/plain",
  html: "text/html",
  csv: "text/csv",
  tsv: "text/tab-separated-values",
  odt: "application/vnd.oasis.opendocument.text",
  ods: "application/vnd.oasis.opendocument.spreadsheet",
  odp: "application/vnd.oasis.opendocument.presentation",
  rtf: "application/rtf",
};

function resolveMime(file: File): string {
  if (file.type && file.type !== "application/octet-stream") return file.type;
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return EXT_TO_MIME[ext] ?? "application/octet-stream";
}

// ─── Types ────────────────────────────────────────────────────────────────────
export interface ParsedPage {
  index: number;
  markdown: string;
  hasEmbeddedImages: boolean;
}

export interface ParseSuccess {
  status: "success";
  engine: "mistral-ocr" | "liteparse" | "mistral-ocr→liteparse-fallback";
  fileName: string;
  mimeType: string;
  fileSize: number;
  pageCount: number;
  truncated: boolean;
  truncatedAt?: number;
  pages: ParsedPage[];
  fullMarkdown: string;
  model?: string;
  usageInfo?: Record<string, unknown>;
}

export interface ParseError {
  status: "error";
  fileName: string;
  error: string;
}

export type ParseResult = ParseSuccess | ParseError;

// ─── Image placeholder replacement (mirrors Python reference notebook) ─────────
function replaceImagePlaceholders(
  markdown: string,
  images: Array<{ id: string; imageBase64?: string | null }>
): string {
  let result = markdown;
  for (const img of images) {
    if (!img.imageBase64) continue;
    // Placeholder format Mistral uses: ![img-0.jpeg](img-0.jpeg)
    result = result.replace(
      new RegExp(`!\\[${escapeRegex(img.id)}\\]\\(${escapeRegex(img.id)}\\)`, "g"),
      `![${img.id}](${img.imageBase64})`
    );
  }
  return result;
}

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// ─── Mistral OCR processor ────────────────────────────────────────────────────
async function runMistralOCR(
  buffer: Buffer,
  mimeType: string,
  fileName: string
): Promise<ParseSuccess> {
  const client = getMistralClient();
  const base64 = buffer.toString("base64");

  const isPdf = mimeType === PDF_MIME_TYPE;
  const document = isPdf
    ? { type: "document_url" as const, documentUrl: `data:application/pdf;base64,${base64}` }
    : { type: "image_url" as const, imageUrl: `data:${mimeType};base64,${base64}` };

  const response = await client.ocr.process({
    model: "mistral-ocr-latest",
    document,
    includeImageBase64: true,
  });

  const allPages = response.pages ?? [];
  const truncated = isPdf && allPages.length > MAX_PDF_PAGES;
  const pagesToProcess = truncated ? allPages.slice(0, MAX_PDF_PAGES) : allPages;

  const pages: ParsedPage[] = pagesToProcess.map((page) => {
    const images = (page.images ?? []) as Array<{ id: string; imageBase64?: string | null }>;
    const markdown = replaceImagePlaceholders(page.markdown ?? "", images);
    return {
      index: page.index,
      markdown,
      hasEmbeddedImages: images.some((img) => !!img.imageBase64),
    };
  });

  const fullMarkdown = pages.map((p) => p.markdown).join("\n\n---\n\n");

  return {
    status: "success",
    engine: "mistral-ocr",
    fileName,
    mimeType,
    fileSize: buffer.length,
    pageCount: pages.length,
    truncated,
    ...(truncated ? { truncatedAt: MAX_PDF_PAGES } : {}),
    pages,
    fullMarkdown,
    model: response.model,
    usageInfo: response.usageInfo as Record<string, unknown> | undefined,
  };
}

// ─── LiteParse processor ───────────────────────────────────────────────────────
async function runLiteParse(
  buffer: Buffer,
  fileName: string,
  mimeType: string
): Promise<ParseSuccess> {
  const parser = new LiteParse({
    ocrEnabled: true,
    outputFormat: "text",
    dpi: 150,
    maxPages: 50, // safety cap
  });

  const result = await parser.parse(buffer);

  const pages: ParsedPage[] = (result.pages ?? []).map((p: Record<string, unknown>, i: number) => {
    const pageNum = typeof p.pageNum === "number" ? p.pageNum : i + 1;
    const textItems = Array.isArray(p.textItems) ? p.textItems : [];
    const text = textItems.map((item: Record<string, unknown>) => item.text ?? "").join(" ");
    return {
      index: pageNum - 1,
      markdown: text,
      hasEmbeddedImages: false,
    };
  });

  const fullMarkdown =
    typeof result.text === "string" && result.text.trim()
      ? result.text
      : pages.map((p) => p.markdown).join("\n\n");

  return {
    status: "success",
    engine: "liteparse",
    fileName,
    mimeType,
    fileSize: buffer.length,
    pageCount: pages.length,
    truncated: false,
    pages,
    fullMarkdown,
  };
}

// ─── Route handler ─────────────────────────────────────────────────────────────
export const maxDuration = 90;

// Allow large multipart bodies (up to 30 MB for multiple 5 MB files)
export const config = {
  api: { bodyParser: false },
};

export async function POST(req: NextRequest) {
  try {
    const contentType = req.headers.get("content-type") ?? "";
    if (!contentType.includes("multipart/form-data")) {
      return NextResponse.json(
        { error: "Expected multipart/form-data." },
        { status: 415 }
      );
    }

    let formData: FormData;
    try {
      formData = await req.formData();
    } catch {
      return NextResponse.json({ error: "Failed to parse form data." }, { status: 400 });
    }

    // Accept both "files" (multi) and "file" (single) field names
    const rawFiles = [
      ...formData.getAll("files"),
      ...formData.getAll("file"),
    ].filter((v): v is File => v instanceof File);

    if (rawFiles.length === 0) {
      return NextResponse.json({ error: "No files provided." }, { status: 400 });
    }

    // Validate: max 5 images
    const imageCount = rawFiles.filter((f) => IMAGE_MIME_TYPES.has(resolveMime(f))).length;
    if (imageCount > MAX_IMAGES_PER_REQUEST) {
      return NextResponse.json(
        { error: `Too many images. You can process at most ${MAX_IMAGES_PER_REQUEST} images at once.` },
        { status: 400 }
      );
    }

    // Process all files concurrently
    const results: ParseResult[] = await Promise.all(
      rawFiles.map(async (file): Promise<ParseResult> => {
        const mimeType = resolveMime(file);
        let buffer: Buffer;

        try {
          buffer = Buffer.from(await file.arrayBuffer());
        } catch {
          return { status: "error", fileName: file.name, error: "Failed to read file buffer." };
        }

        // Size guard
        if (buffer.length > MAX_FILE_SIZE_BYTES) {
          return {
            status: "error",
            fileName: file.name,
            error: `File is too large (${(buffer.length / 1024 / 1024).toFixed(2)} MB). Maximum allowed size is 5 MB.`,
          };
        }

        const useMistral = mimeType === PDF_MIME_TYPE || IMAGE_MIME_TYPES.has(mimeType);

        if (useMistral) {
          try {
            return await runMistralOCR(buffer, mimeType, file.name);
          } catch (mistralErr) {
            console.warn(
              `[parse] Mistral OCR failed for "${file.name}", falling back to LiteParse.`,
              mistralErr instanceof Error ? mistralErr.message : mistralErr
            );
            try {
              const fallback = await runLiteParse(buffer, file.name, mimeType);
              return { ...fallback, engine: "mistral-ocr→liteparse-fallback" };
            } catch (lpErr) {
              return {
                status: "error",
                fileName: file.name,
                error: `Mistral OCR failed (${mistralErr instanceof Error ? mistralErr.message : "unknown"}) and LiteParse fallback also failed (${lpErr instanceof Error ? lpErr.message : "unknown"}).`,
              };
            }
          }
        }

        // Docs, spreadsheets, presentations → LiteParse
        try {
          return await runLiteParse(buffer, file.name, mimeType);
        } catch (err) {
          return {
            status: "error",
            fileName: file.name,
            error: `LiteParse failed: ${err instanceof Error ? err.message : "Unknown error."}`,
          };
        }
      })
    );

    return NextResponse.json({ results }, { status: 200 });
  } catch (err) {
    console.error("[parse API] Unhandled error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unexpected server error." },
      { status: 500 }
    );
  }
}