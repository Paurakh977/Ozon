import { Controller } from '@nestjs/common';
import { RateLimitService } from './ratelimit.service';

@Controller('ratelimit')
export class RatelimitController {
  constructor(private readonly ratelimitService: RateLimitService) {}
}
