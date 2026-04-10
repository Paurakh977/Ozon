import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Mistral } from '@mistralai/mistralai';
import {
  MAX_FILE_SIZE_BYTES,
  MAX_PDF_PAGES,
  PDF_MIME_TYPE,
  IMAGE_MIME_TYPES,
  resolveMime,
} from './parse.constants';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ParsedPage {
  index: number;
  markdown: string;
  hasEmbeddedImages: boolean;
}

interface ParseSuccess {
  status: 'success';
  engine: 'mistral-ocr' | 'liteparse' | 'mistral-ocr→liteparse-fallback';
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

interface ParseError {
  status: 'error';
  fileName: string;
  error: string;
}

export type ParseResult = ParseSuccess | ParseError;

// LiteParse page shape — avoids `any`
interface LitePageItem {
  pageNum?: number;
  textItems?: Array<{ text?: string }>;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function replaceImagePlaceholders(
  markdown: string,
  images: Array<{ id: string; imageBase64?: string | null }>,
): string {
  let result = markdown;
  for (const img of images) {
    if (!img.imageBase64) continue;
    result = result.replace(
      new RegExp(
        `!\\[${escapeRegex(img.id)}\\]\\(${escapeRegex(img.id)}\\)`,
        'g',
      ),
      `![${img.id}](${img.imageBase64})`,
    );
  }
  return result;
}

// ─── Service ──────────────────────────────────────────────────────────────────

@Injectable()
export class ParseService {
  private readonly logger = new Logger(ParseService.name);

  // Lazy singletons — initialised once and reused for the lifetime of the service
  private mistralClient: Mistral | null = null;
  // LiteParse is a dynamic import; cache the class so we only pay the import
  // cost once rather than on every parse call.
  private LiteParseClass: (new (opts: LiteParseOptions) => LiteParseInstance) | null = null;

  constructor(private readonly configService: ConfigService) {}

  // ─── Public API ─────────────────────────────────────────────────────────────

  async parseFile(
    buffer: Buffer,
    fileName: string,
    mimeType: string,
  ): Promise<ParseResult> {
    const resolvedMime = resolveMime(fileName, mimeType);

    if (buffer.length > MAX_FILE_SIZE_BYTES) {
      return {
        status: 'error',
        fileName,
        error: `File is too large (${(buffer.length / 1024 / 1024).toFixed(2)} MB). Maximum allowed size is 5 MB.`,
      };
    }

    const useMistral =
      resolvedMime === PDF_MIME_TYPE || IMAGE_MIME_TYPES.has(resolvedMime);

    if (useMistral) {
      try {
        return await this.runMistralOCR(buffer, resolvedMime, fileName);
      } catch (mistralErr) {
        this.logger.warn(
          `Mistral OCR failed for "${fileName}", falling back to LiteParse — ${
            mistralErr instanceof Error ? mistralErr.message : String(mistralErr)
          }`,
        );
        try {
          const fallback = await this.runLiteParse(buffer, fileName, resolvedMime);
          return { ...fallback, engine: 'mistral-ocr→liteparse-fallback' };
        } catch (lpErr) {
          return {
            status: 'error',
            fileName,
            error:
              `Mistral OCR failed (${mistralErr instanceof Error ? mistralErr.message : 'unknown'})` +
              ` and LiteParse fallback also failed (${lpErr instanceof Error ? lpErr.message : 'unknown'}).`,
          };
        }
      }
    }

    try {
      return await this.runLiteParse(buffer, fileName, resolvedMime);
    } catch (err) {
      return {
        status: 'error',
        fileName,
        error: `LiteParse failed: ${err instanceof Error ? err.message : 'Unknown error.'}`,
      };
    }
  }

  // ─── Private helpers ─────────────────────────────────────────────────────────

  private getMistralClient(): Mistral {
    if (!this.mistralClient) {
      const apiKey = this.configService.getOrThrow<string>('MISTRAL_API_KEY');
      this.mistralClient = new Mistral({ apiKey });
    }
    return this.mistralClient;
  }

  /** Import LiteParse once, then reuse the class on subsequent calls. */
  private async getLiteParseClass(): Promise<
    new (opts: LiteParseOptions) => LiteParseInstance
  > {
    if (!this.LiteParseClass) {
      const mod = await import('@llamaindex/liteparse');
      // The upstream LiteParse constructor has a slightly different
      // parameter shape; cast to our minimal constructor type to
      // avoid a strict mismatch while keeping runtime behavior.
      this.LiteParseClass = mod.LiteParse as unknown as new (
        opts: LiteParseOptions,
      ) => LiteParseInstance;
    }
    return this.LiteParseClass as new (opts: LiteParseOptions) => LiteParseInstance;
  }

  private async runMistralOCR(
    buffer: Buffer,
    mimeType: string,
    fileName: string,
  ): Promise<ParseSuccess> {
    const client = this.getMistralClient();
    const base64 = buffer.toString('base64');
    const isPdf = mimeType === PDF_MIME_TYPE;

    const document = isPdf
      ? {
          type: 'document_url' as const,
          documentUrl: `data:application/pdf;base64,${base64}`,
        }
      : {
          type: 'image_url' as const,
          imageUrl: `data:${mimeType};base64,${base64}`,
        };

    const response = await client.ocr.process({
      model: 'mistral-ocr-latest',
      document,
      includeImageBase64: true,
    });

    const allPages = response.pages ?? [];
    const truncated = isPdf && allPages.length > MAX_PDF_PAGES;
    const pagesToProcess = truncated ? allPages.slice(0, MAX_PDF_PAGES) : allPages;

    const pages: ParsedPage[] = pagesToProcess.map((page) => {
      const images = (page.images ?? []) as Array<{
        id: string;
        imageBase64?: string | null;
      }>;
      const markdown = replaceImagePlaceholders(page.markdown ?? '', images);
      return {
        index: page.index,
        markdown,
        hasEmbeddedImages: images.some((img) => !!img.imageBase64),
      };
    });

    return {
      status: 'success',
      engine: 'mistral-ocr',
      fileName,
      mimeType,
      fileSize: buffer.length,
      pageCount: pages.length,
      truncated,
      ...(truncated ? { truncatedAt: MAX_PDF_PAGES } : {}),
      pages,
      fullMarkdown: pages.map((p) => p.markdown).join('\n\n---\n\n'),
      model: response.model,
      usageInfo: response.usageInfo as Record<string, unknown> | undefined,
    };
  }

  private async runLiteParse(
    buffer: Buffer,
    fileName: string,
    mimeType: string,
  ): Promise<ParseSuccess> {
    const LiteParse = await this.getLiteParseClass();
    const parser = new LiteParse({
      ocrEnabled: true,
      outputFormat: 'text',
      dpi: 150,
      maxPages: 50,
    });

    const result = await parser.parse(buffer);

    const pages: ParsedPage[] = (result.pages ?? []).map(
      (p: LitePageItem, i: number) => {
        const pageNum = typeof p.pageNum === 'number' ? p.pageNum : i + 1;
        const text = (p.textItems ?? [])
          .map((item) => item.text ?? '')
          .join(' ');
        return { index: pageNum - 1, markdown: text, hasEmbeddedImages: false };
      },
    );

    const fullMarkdown =
      typeof result.text === 'string' && result.text.trim()
        ? result.text
        : pages.map((p) => p.markdown).join('\n\n');

    return {
      status: 'success',
      engine: 'liteparse',
      fileName,
      mimeType,
      fileSize: buffer.length,
      pageCount: pages.length,
      truncated: false,
      pages,
      fullMarkdown,
    };
  }
}

// ─── Minimal LiteParse interface shapes (avoids `any`) ───────────────────────

interface LiteParseOptions {
  ocrEnabled?: boolean;
  outputFormat?: string;
  dpi?: number;
  maxPages?: number;
}

interface LiteParseResult {
  text?: string;
  pages?: LitePageItem[];
}

interface LiteParseInstance {
  parse(buffer: Buffer): Promise<LiteParseResult>;
}