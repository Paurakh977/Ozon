import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

// If Deepgram doesn't respond within this window, abort and surface an error
// rather than hanging the client indefinitely.
const DEEPGRAM_TIMEOUT_MS = 10_000;

@Injectable()
export class SttService {
  private readonly logger = new Logger(SttService.name);

  // Read once at construction — avoids repeated env lookups per request
  private readonly apiKey: string;
  private readonly projectId: string;

  constructor(private readonly configService: ConfigService) {
    // ConfigModule validation in app.module guarantees these exist
    this.apiKey = this.configService.getOrThrow<string>('DEEPGRAM_API_KEY');
    this.projectId = this.configService.getOrThrow<string>('DEEPGRAM_PROJECT_ID');
  }

  async createDeepgramKey(): Promise<{ key: string }> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), DEEPGRAM_TIMEOUT_MS);

    let response: Response;
    try {
      response = await fetch(
        `https://api.deepgram.com/v1/projects/${this.projectId}/keys`,
        {
          method: 'POST',
          headers: {
            Authorization: `Token ${this.apiKey}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            comment: 'Temporary client key for STT',
            scopes: ['member'],
            time_to_live_in_seconds: 60,
          }),
          signal: controller.signal,
        },
      );
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        throw new Error('Deepgram API timed out');
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }

    if (!response.ok) {
      let detail: unknown = response.statusText;
      try {
        detail = await response.json();
      } catch {
        // ignore parse error — statusText is good enough for the log
      }
      this.logger.error(`Deepgram API error ${response.status}:`, detail);
      throw new Error(`Failed to create temporary key (HTTP ${response.status})`);
    }

    const data: unknown = await response.json();
    const keyValue = this.extractKey(data);

    if (!keyValue) {
      this.logger.error('Deepgram returned unexpected payload:', data);
      throw new Error('Deepgram did not return a usable temporary key');
    }

    return { key: keyValue };
  }

  /**
   * Deepgram's key-creation endpoint has historically returned the key
   * in slightly different shapes. Handle them all in one place.
   */
  private extractKey(data: unknown): string | null {
    if (!data || typeof data !== 'object') return null;
    const d = data as Record<string, unknown>;

    if (typeof d.api_key === 'string') return d.api_key;

    if (d.api_key && typeof d.api_key === 'object') {
      const nested = d.api_key as Record<string, unknown>;
      if (typeof nested.api_key === 'string') return nested.api_key;
      if (typeof nested.token === 'string') return nested.token;
    }

    if (typeof d.key === 'string') return d.key;
    if (typeof d.apiKey === 'string') return d.apiKey;

    return null;
  }
}