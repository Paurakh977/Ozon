import {
  Controller,
  Get,
  Req,
  HttpCode,
  HttpStatus,
  HttpException,
  Logger,
} from '@nestjs/common';
import type { Request } from 'express';
import { Session, type UserSession } from '@thallesp/nestjs-better-auth';
import { SttService } from './stt.service';
import { RateLimitService } from '../ratelimit/ratelimit.service';

/**
 * GET /api/stt
 *
 * Protected by the global AuthGuard (requires a valid Better Auth session).
 * Issues a short-lived Deepgram temporary key for the authenticated user.
 *
 * Rate limit: per-userId sliding window (Redis-backed).
 * Fallback to IP when userId is unavailable (should never happen post-auth).
 */
@Controller('stt')
export class SttController {
  private readonly logger = new Logger(SttController.name);

  constructor(
    private readonly sttService: SttService,
    private readonly rateLimitService: RateLimitService,
  ) {}

  @Get()
  @HttpCode(HttpStatus.OK)
  async createKey(
    @Session() session: UserSession,
    @Req() req: Request,
  ) {
    // Prefer stable userId over IP — prevents VPN-rotation bypass
    const identifier = session.user.id ?? this.resolveIp(req);

    const allowed = await this.rateLimitService.check(identifier, 'stt');
    if (!allowed) {
      this.logger.warn(
        `STT rate limit exceeded — userId: ${session.user.id}, IP: ${this.resolveIp(req)}`,
      );
      throw new HttpException(
        { error: 'Rate limit exceeded. Please wait before requesting another key.' },
        HttpStatus.TOO_MANY_REQUESTS,
      );
    }

    try {
      return await this.sttService.createDeepgramKey();
    } catch (error) {
      this.logger.error(
        'Failed to generate Deepgram key',
        error instanceof Error ? error.stack : String(error),
      );
      throw new HttpException(
        {
          error:
            error instanceof Error ? error.message : 'Internal Server Error',
        },
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /** Best-effort IP extraction; handles proxies and IPv6-mapped IPv4. */
  private resolveIp(req: Request): string {
    const fwd = req.headers['x-forwarded-for'];
    const firstFwd = (Array.isArray(fwd) ? fwd[0] : fwd)
      ?.split(',')[0]
      ?.trim();
    const realIp = req.headers['x-real-ip'];
    const firstReal = Array.isArray(realIp) ? realIp[0] : realIp;
    return firstFwd ?? firstReal ?? req.socket?.remoteAddress ?? 'unknown';
  }
}