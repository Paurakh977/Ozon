import { Module } from '@nestjs/common';
import { RateLimitService } from './ratelimit.service';
import { RatelimitController } from './ratelimit.controller';

@Module({
  controllers: [RatelimitController],
  providers: [RateLimitService],
})
export class RatelimitModule {}
