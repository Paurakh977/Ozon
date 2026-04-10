import { Module } from '@nestjs/common';
import { MulterModule } from '@nestjs/platform-express';
import { memoryStorage } from 'multer';
import { ParseController } from './parse.controller';
import { ParseService } from './parse.service';
import { MAX_FILE_SIZE_BYTES, MAX_FILES_PER_REQUEST } from './parse.constants';

@Module({
  imports: [
    MulterModule.register({
      // Keep files in-memory as Buffers — no temp files on disk
      storage: memoryStorage(),
      limits: {
        // Hard reject at the HTTP layer before the buffer even lands in the service
        fileSize: MAX_FILE_SIZE_BYTES,
        files: MAX_FILES_PER_REQUEST,
      },
    }),
  ],
  controllers: [ParseController],
  providers: [ParseService],
})
export class ParseModule {}