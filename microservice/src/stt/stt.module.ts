import { Module } from '@nestjs/common';
import { SttController } from './stt.controller';
import { SttService } from './stt.service';
import { RatelimitModule } from '../ratelimit/ratelimit.module';

/**
 * SttModule imports RatelimitModule so it can inject RateLimitService.
 * RedisModule is @Global(), so no explicit import needed here.
 */
@Module({
  imports: [RatelimitModule],
  controllers: [SttController],
  providers: [SttService],
})
export class SttModule {}