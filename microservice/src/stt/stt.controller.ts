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
import { SttService } from './stt.service';
import { RateLimitService } from '../ratelimit/ratelimit.service';


@Controller('stt')
export class SttController {
  private readonly logger = new Logger(SttController.name);

  constructor(
    private readonly sttService: SttService,
    private readonly rateLimitService: RateLimitService,
  ) {}

  @Get()
  @HttpCode(HttpStatus.OK)
  async createKey(@Req() req: Request) {
    const ip = this.resolveIp(req);

    if (!this.rateLimitService.check(ip)) {
      this.logger.warn(`Rate limit exceeded — IP: ${ip}`);
      throw new HttpException(
        { error: 'Rate limit exceeded' },
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
        { error: error instanceof Error ? error.message : 'Internal Server Error' },
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /** Best-effort IP extraction; handles proxies and IPv6-mapped IPv4. */
  private resolveIp(req: Request): string {
    const fwd = req.headers['x-forwarded-for'];
    const firstFwd = (Array.isArray(fwd) ? fwd[0] : fwd)?.split(',')[0]?.trim();
    const realIp = req.headers['x-real-ip'];
    const firstReal = Array.isArray(realIp) ? realIp[0] : realIp;
    return firstFwd ?? firstReal ?? req.socket?.remoteAddress ?? 'unknown';
  }
}