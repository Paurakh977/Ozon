import {
  Controller,
  Post,
  HttpCode,
  HttpStatus,
  HttpException,
  UseInterceptors,
  UploadedFiles,
  Logger,
  BadRequestException,
} from '@nestjs/common';
import { FilesInterceptor } from '@nestjs/platform-express';
import { MulterError } from 'multer';
import { Session, type UserSession } from '@thallesp/nestjs-better-auth';
import { ParseService } from './parse.service';
import { RateLimitService } from '../ratelimit/ratelimit.service';
import {
  MAX_FILES_PER_REQUEST,
  MAX_IMAGES_PER_REQUEST,
  IMAGE_MIME_TYPES,
  resolveMime,
} from './parse.constants';

/**
 * POST /api/parse
 *
 * Protected by the global AuthGuard (requires a valid Better Auth session).
 * Accepts multipart file uploads and parses them via Mistral OCR.
 *
 * Rate limit: per-userId sliding window (Redis-backed).
 * File-level limits (size, count) are enforced by Multer in parse.module.ts.
 */
@Controller('parse')
export class ParseController {
  private readonly logger = new Logger(ParseController.name);

  constructor(
    private readonly parseService: ParseService,
    private readonly rateLimitService: RateLimitService,
  ) {}

  @Post()
  @HttpCode(HttpStatus.OK)
  @UseInterceptors(FilesInterceptor('file', MAX_FILES_PER_REQUEST))
  async parseFiles(
    @UploadedFiles() files: Express.Multer.File[],
    @Session() session: UserSession,
  ) {
    // Rate-limit by userId — prevents API key abuse, survives scaling
    const allowed = await this.rateLimitService.check(session.user.id, 'parse');
    if (!allowed) {
      this.logger.warn(
        `Parse rate limit exceeded — userId: ${session.user.id}`,
      );
      throw new HttpException(
        { error: 'Rate limit exceeded. Please wait before uploading more files.' },
        HttpStatus.TOO_MANY_REQUESTS,
      );
    }

    const fileList = files ?? [];

    if (fileList.length === 0) {
      throw new HttpException(
        { error: 'No files provided.' },
        HttpStatus.BAD_REQUEST,
      );
    }

    // Mirror the original per-request image limit
    const imageCount = fileList.filter((f) =>
      IMAGE_MIME_TYPES.has(resolveMime(f.originalname, f.mimetype)),
    ).length;

    if (imageCount > MAX_IMAGES_PER_REQUEST) {
      throw new HttpException(
        {
          error: `Too many images. Maximum ${MAX_IMAGES_PER_REQUEST} images allowed per request.`,
        },
        HttpStatus.BAD_REQUEST,
      );
    }

    try {
      const results = await Promise.all(
        fileList.map((file) =>
          this.parseService.parseFile(
            file.buffer,
            file.originalname,
            file.mimetype,
          ),
        ),
      );
      return { results };
    } catch (err) {
      if (err instanceof MulterError) {
        throw new BadRequestException(this.multerErrorMessage(err));
      }
      this.logger.error(
        'Unhandled error in parseFiles',
        err instanceof Error ? err.stack : err,
      );
      throw new HttpException(
        { error: 'Unexpected server error.' },
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  private multerErrorMessage(err: MulterError): string {
    switch (err.code) {
      case 'LIMIT_FILE_SIZE':
        return 'File is too large. Maximum allowed size is 5 MB per file.';
      case 'LIMIT_FILE_COUNT':
        return `Too many files. Maximum ${MAX_FILES_PER_REQUEST} files allowed.`;
      case 'LIMIT_UNEXPECTED_FILE':
        return 'Unexpected file field. Use the "file" field name.';
      default:
        return `Upload error: ${err.message}`;
    }
  }
}