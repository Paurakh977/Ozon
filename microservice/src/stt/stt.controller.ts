import { Controller, Get, Req, HttpCode, HttpStatus, HttpException } from '@nestjs/common';
import { SttService } from './stt.service';
import type { Request } from 'express';

@Controller('stt')
export class SttController {
  constructor(private readonly sttService: SttService) {}

  @Get()
  @HttpCode(HttpStatus.OK)
  async createKey(@Req() req: Request) {
    const apiKey = process.env.DEEPGRAM_API_KEY;
    const projectId = process.env.DEEPGRAM_PROJECT_ID;

    if (!apiKey || !projectId) {
      throw new HttpException(
        { error: 'Deepgram environment variables are missing.' },
        HttpStatus.INTERNAL_SERVER_ERROR
      );
    }

    const allowedOrigin = process.env.NEXT_PUBLIC_APP_URL;
    const headers = req.headers as Record<string, string | string[] | undefined>;
    const origin = (Array.isArray(headers.origin) ? headers.origin[0] : headers.origin) || 
                  (Array.isArray(headers.referer) ? headers.referer[0] : headers.referer) || '';
    if (allowedOrigin && origin && !origin.includes(allowedOrigin)) {
      console.warn('Blocked key request from disallowed origin:', origin);
      throw new HttpException({ error: 'Forbidden' }, HttpStatus.FORBIDDEN);
    }

    const forwarded = (Array.isArray(headers['x-forwarded-for']) ? headers['x-forwarded-for'][0] : headers['x-forwarded-for']) || '';
    const ip = (forwarded.split(',')[0] || 
               (Array.isArray(headers['x-real-ip']) ? headers['x-real-ip'][0] : headers['x-real-ip']) || 
               'unknown').trim();

    const maxKeysPerWindow = process.env.SST_MAX_KEYS_PER_WINDOW;
    const windowMs = process.env.SST_KEY_WINDOW_MS;
    
    if (!maxKeysPerWindow || !windowMs) {
      throw new HttpException(
        { error: 'Rate limit configuration is missing.' },
        HttpStatus.INTERNAL_SERVER_ERROR
      );
    }

    const MAX_KEYS_PER_WINDOW = parseInt(maxKeysPerWindow, 10);
    const WINDOW_MS = parseInt(windowMs, 10);

    if (!globalThis.__dg_sst_rate_map) {
      (globalThis as any).__dg_sst_rate_map = new Map();
    }
    const rateMap: Map<string, number[]> = (globalThis as any).__dg_sst_rate_map;
    const now = Date.now();
    const windowKey = `sst:${ip}`;
    const recent = (rateMap.get(windowKey) || []).filter((t) => now - t < WINDOW_MS);
    if (recent.length >= MAX_KEYS_PER_WINDOW) {
      console.warn(`Rate limit exceeded for IP ${ip}`);
      throw new HttpException({ error: 'Rate limit exceeded' }, HttpStatus.TOO_MANY_REQUESTS);
    }
    recent.push(now);
    rateMap.set(windowKey, recent);

    try {
      const result = await this.sttService.createDeepgramKey();
      return result;
    } catch (error) {
      console.error('Network error generating Deepgram key:', error);
      throw new HttpException(
        { error: error instanceof Error ? error.message : 'Internal Server Error' },
        HttpStatus.INTERNAL_SERVER_ERROR
      );
    }
  }
}