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
import { ParseService } from './parse.service';
import {
  MAX_FILES_PER_REQUEST,
  MAX_IMAGES_PER_REQUEST,
  IMAGE_MIME_TYPES,
  resolveMime,
} from './parse.constants';

@Controller('parse')
export class ParseController {
  private readonly logger = new Logger(ParseController.name);

  constructor(private readonly parseService: ParseService) {}

  @Post()
  @HttpCode(HttpStatus.OK)
  // File size + file count limits are enforced at the multer level (parse.module.ts).
  // The interceptor here just picks up the already-validated buffers.
  @UseInterceptors(FilesInterceptor('file', MAX_FILES_PER_REQUEST))
  async parseFiles(@UploadedFiles() files: Express.Multer.File[]) {
    const fileList = files ?? [];

    if (fileList.length === 0) {
      throw new HttpException({ error: 'No files provided.' }, HttpStatus.BAD_REQUEST);
    }

    // Mirror the original Next.js route's per-request image limit
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
          // file.buffer is already a Buffer from multer — no need for Buffer.from()
          this.parseService.parseFile(file.buffer, file.originalname, file.mimetype),
        ),
      );
      return { results };
    } catch (err) {
      // Surface multer errors (e.g. LIMIT_FILE_SIZE) as clean 400s
      if (err instanceof MulterError) {
        throw new BadRequestException(this.multerErrorMessage(err));
      }
      this.logger.error('Unhandled error in parseFiles', err instanceof Error ? err.stack : err);
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