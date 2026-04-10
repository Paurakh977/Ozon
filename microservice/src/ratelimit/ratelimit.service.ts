import { Injectable, OnModuleDestroy, OnModuleInit, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class RateLimitService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(RateLimitService.name);

  // ip-keyed map of request timestamps within the current window
  private readonly rateMap = new Map<string, number[]>();
  private cleanupTimer: NodeJS.Timeout;

  private readonly maxKeysPerWindow: number;
  private readonly windowMs: number;

  constructor(private readonly configService: ConfigService) {
    this.maxKeysPerWindow = this.configService.get<number>(
      'SST_MAX_KEYS_PER_WINDOW',
      6,
    );
    this.windowMs = this.configService.get<number>('SST_KEY_WINDOW_MS', 60_000);
  }

  onModuleInit() {
    // Sweep the map once per window to evict fully-expired IPs.
    // Without this, every unique IP that ever hit the service would stay in memory.
    this.cleanupTimer = setInterval(() => {
      const now = Date.now();
      let evicted = 0;
      for (const [key, timestamps] of this.rateMap) {
        const fresh = timestamps.filter((t) => now - t < this.windowMs);
        if (fresh.length === 0) {
          this.rateMap.delete(key);
          evicted++;
        } else {
          this.rateMap.set(key, fresh);
        }
      }
      if (evicted > 0) {
        this.logger.debug(`Rate-limit map: evicted ${evicted} stale entries`);
      }
    }, this.windowMs);

    // Don't keep the event-loop alive just for housekeeping
    this.cleanupTimer.unref();
  }

  onModuleDestroy() {
    clearInterval(this.cleanupTimer);
  }

  /**
   * Returns `true` when the request is within the allowed rate, `false` when limited.
   * Increments the counter on every allowed request.
   */
  check(ip: string): boolean {
    const now = Date.now();
    const key = `sst:${ip}`;
    const recent = (this.rateMap.get(key) ?? []).filter(
      (t) => now - t < this.windowMs,
    );

    if (recent.length >= this.maxKeysPerWindow) {
      return false;
    }

    recent.push(now);
    this.rateMap.set(key, recent);
    return true;
  }
}