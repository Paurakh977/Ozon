import { Controller, Get } from '@nestjs/common';
import { AllowAnonymous } from '@thallesp/nestjs-better-auth';
import { RateLimitService } from './ratelimit.service';

/**
 * Internal admin endpoint — no public rate-check endpoint is exposed.
 * The /api/ratelimit/health route is anonymous for load-balancer probes only.
 * All business rate-limit logic lives in the service and is used by other controllers.
 */
@Controller('ratelimit')
export class RatelimitController {
  constructor(private readonly ratelimitService: RateLimitService) {}

  /** Load-balancer / Docker healthcheck probe — no auth needed */
  @Get('health')
  @AllowAnonymous()
  health() {
    return { status: 'ok' };
  }
}
