import { NextRequest, NextResponse } from "next/server";
import { LiteParse } from "@llamaindex/liteparse";

// Increase payload size limit for large files (Next.js 13+ app router config)
export const maxDuration = 60; // 60s timeout for heavy OCR

export async function POST(req: NextRequest) {
  try {
    const contentType = req.headers.get("content-type") || "";

    let fileBuffer: Buffer;
    let fileName = "document";

    // ── URL mode ──────────────────────────────────────────────────────────────
    if (contentType.includes("application/json")) {
      const body = await req.json();
      const url: string = body?.url;

      if (!url || !/^https?:\/\/.+/i.test(url)) {
        return NextResponse.json({ error: "Invalid or missing URL." }, { status: 400 });
      }

      const fetchRes = await fetch(url, {
        headers: { "User-Agent": "LiteParse/1.0" },
      });

      if (!fetchRes.ok) {
        return NextResponse.json(
          { error: `Failed to fetch URL: ${fetchRes.statusText}` },
          { status: 400 }
        );
      }

      const arrayBuffer = await fetchRes.arrayBuffer();
      fileBuffer = Buffer.from(arrayBuffer);
      fileName = url.split("/").pop()?.split("?")[0] || "remote-document";

    // ── File upload mode ──────────────────────────────────────────────────────
    } else if (contentType.includes("multipart/form-data")) {
      const formData = await req.formData();
      const file = formData.get("file") as File | null;

      if (!file) {
        return NextResponse.json({ error: "No file provided." }, { status: 400 });
      }

      const arrayBuffer = await file.arrayBuffer();
      fileBuffer = Buffer.from(arrayBuffer);
      fileName = file.name;

    } else {
      return NextResponse.json({ error: "Unsupported content type." }, { status: 415 });
    }

    // ── Parse ─────────────────────────────────────────────────────────────────
    const parser = new LiteParse({
      ocrEnabled: true,        // Tesseract.js handles scanned docs & images
      outputFormat: "text",
      dpi: 150,
    });

    const result = await parser.parse(fileBuffer);

    const pages = result.pages.map((p) => ({
      pageNum: p.pageNum,
      itemCount: p.textItems.length,
    }));

    return NextResponse.json({
      text: result.text,
      fileName,
      pageCount: result.pages.length,
      pages,
    });

  } catch (err: unknown) {
    console.error("[LiteParse API Error]", err);
    const message =
      err instanceof Error ? err.message : "Unexpected server error.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}