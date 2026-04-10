import { Module } from '@nestjs/common';
import { SttController } from './stt.controller';
import { SttService } from './stt.service';

@Module({
  controllers: [SttController],
  providers: [SttService],
})
export class SttModule {}