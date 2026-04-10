import { Module } from '@nestjs/common';
import { SttController } from './stt.controller';
import { SttService } from './stt.service';
import { RateLimitService } from '../ratelimit/ratelimit.service';

@Module({
  controllers: [SttController],
  providers: [SttService, RateLimitService],
})
export class SttModule {}