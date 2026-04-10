import {
  Controller,
  Post,
  HttpCode,
  HttpStatus,
  HttpException,
  UseInterceptors,
  UploadedFiles,
  Body,
} from '@nestjs/common';
import { FilesInterceptor } from '@nestjs/platform-express';
import { ParseService } from './parse.service';

@Controller('parse')
export class ParseController {
  constructor(private readonly parseService: ParseService) {}

  @Post()
  @HttpCode(HttpStatus.OK)
  @UseInterceptors(FilesInterceptor('file', 10))
  async parseFiles(@UploadedFiles() files: Express.Multer.File[]) {
    let fileList: Express.Multer.File[] = files || [];

    if (fileList.length === 0) {
      throw new HttpException({ error: 'No files provided.' }, HttpStatus.BAD_REQUEST);
    }

    if (fileList.length > 10) {
      throw new HttpException(
        { error: 'Too many files. Maximum 10 files allowed.' },
        HttpStatus.BAD_REQUEST
      );
    }

    const results = await Promise.all(
      fileList.map(async (file) => {
        const buffer = Buffer.from(file.buffer);
        return this.parseService.parseFile(buffer, file.originalname, file.mimetype);
      })
    );

    return { results };
  }
}