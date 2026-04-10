import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Mistral } from '@mistralai/mistralai';

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

const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024;
const MAX_PDF_PAGES = 5;
const MAX_IMAGES_PER_REQUEST = 5;

const IMAGE_MIME_TYPES = new Set([
  'image/jpeg',
  'image/jpg',
  'image/png',
  'image/webp',
  'image/avif',
  'image/gif',
  'image/tiff',
  'image/bmp',
]);

const PDF_MIME_TYPE = 'application/pdf';

const EXT_TO_MIME: Record<string, string> = {
  pdf: 'application/pdf',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  avif: 'image/avif',
  gif: 'image/gif',
  tiff: 'image/tiff',
  bmp: 'image/bmp',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  doc: 'application/msword',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  xls: 'application/vnd.ms-excel',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  ppt: 'application/vnd.ms-powerpoint',
  txt: 'text/plain',
  html: 'text/html',
  csv: 'text/csv',
  tsv: 'text/tab-separated-values',
  odt: 'application/vnd.oasis.opendocument.text',
  ods: 'application/vnd.oasis.opendocument.spreadsheet',
  odp: 'application/vnd.oasis.opendocument.presentation',
  rtf: 'application/rtf',
};

function resolveMime(fileName: string, mimeType: string): string {
  if (mimeType && mimeType !== 'application/octet-stream') return mimeType;
  const ext = fileName.split('.').pop()?.toLowerCase() ?? '';
  return EXT_TO_MIME[ext] ?? 'application/octet-stream';
}

function replaceImagePlaceholders(
  markdown: string,
  images: Array<{ id: string; imageBase64?: string | null }>
): string {
  let result = markdown;
  for (const img of images) {
    if (!img.imageBase64) continue;
    result = result.replace(
      new RegExp(`!\\[${escapeRegex(img.id)}\\]\\(${escapeRegex(img.id)}\\)`, 'g'),
      `![${img.id}](${img.imageBase64})`
    );
  }
  return result;
}

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

@Injectable()
export class ParseService {
  private mistral: Mistral | null = null;

  constructor(private configService: ConfigService) {}

  private getMistralClient(): Mistral {
    if (!this.mistral) {
      const apiKey = this.configService.get<string>('MISTRAL_API_KEY');
      if (!apiKey) throw new Error('MISTRAL_API_KEY is not set in environment variables.');
      this.mistral = new Mistral({ apiKey });
    }
    return this.mistral;
  }

  async parseFile(buffer: Buffer, fileName: string, mimeType: string): Promise<ParseResult> {
    const resolvedMime = resolveMime(fileName, mimeType);

    if (buffer.length > MAX_FILE_SIZE_BYTES) {
      return {
        status: 'error',
        fileName,
        error: `File is too large (${(buffer.length / 1024 / 1024).toFixed(2)} MB). Maximum allowed size is 5 MB.`,
      };
    }

    const useMistral = resolvedMime === PDF_MIME_TYPE || IMAGE_MIME_TYPES.has(resolvedMime);

    if (useMistral) {
      try {
        return await this.runMistralOCR(buffer, resolvedMime, fileName);
      } catch (mistralErr) {
        console.warn(
          `[parse] Mistral OCR failed for "${fileName}", falling back to LiteParse.`,
          mistralErr instanceof Error ? mistralErr.message : mistralErr
        );
        try {
          const fallback = await this.runLiteParse(buffer, fileName, resolvedMime);
          return { ...fallback, engine: 'mistral-ocr→liteparse-fallback' };
        } catch (lpErr) {
          return {
            status: 'error',
            fileName,
            error: `Mistral OCR failed (${
              mistralErr instanceof Error ? mistralErr.message : 'unknown'
            }) and LiteParse fallback also failed (${
              lpErr instanceof Error ? lpErr.message : 'unknown'
            }).`,
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

  private async runMistralOCR(
    buffer: Buffer,
    mimeType: string,
    fileName: string
  ): Promise<ParseSuccess> {
    const client = this.getMistralClient();
    const base64 = buffer.toString('base64');

    const isPdf = mimeType === PDF_MIME_TYPE;
    const document = isPdf
      ? { type: 'document_url' as const, documentUrl: `data:application/pdf;base64,${base64}` }
      : { type: 'image_url' as const, imageUrl: `data:${mimeType};base64,${base64}` };

    const response = await client.ocr.process({
      model: 'mistral-ocr-latest',
      document,
      includeImageBase64: true,
    });

    const allPages = response.pages ?? [];
    const truncated = isPdf && allPages.length > MAX_PDF_PAGES;
    const pagesToProcess = truncated ? allPages.slice(0, MAX_PDF_PAGES) : allPages;

    const pages: ParsedPage[] = pagesToProcess.map((page) => {
      const images = page.images ?? [];
      const markdown = replaceImagePlaceholders(page.markdown ?? '', images);
      return {
        index: page.index,
        markdown,
        hasEmbeddedImages: images.some((img) => !!img.imageBase64),
      };
    });

    const fullMarkdown = pages.map((p) => p.markdown).join('\n\n---\n\n');

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
      fullMarkdown,
      model: response.model,
      usageInfo: response.usageInfo as Record<string, unknown> | undefined,
    };
  }

  private async runLiteParse(
    buffer: Buffer,
    fileName: string,
    mimeType: string
  ): Promise<ParseSuccess> {
    const { LiteParse } = await import('@llamaindex/liteparse');
    const parser = new LiteParse({
      ocrEnabled: true,
      outputFormat: 'text',
      dpi: 150,
      maxPages: 50,
    });

    const result = await parser.parse(buffer);

    const pages: ParsedPage[] = (result.pages ?? []).map((p: any, i: number) => {
      const pageNum = typeof p.pageNum === 'number' ? p.pageNum : i + 1;
      const textItems = Array.isArray(p.textItems) ? p.textItems : [];
      const text = textItems.map((item: any) => item.text ?? '').join(' ');
      return {
        index: pageNum - 1,
        markdown: text,
        hasEmbeddedImages: false,
      };
    });

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