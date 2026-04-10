import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class SttService {
  constructor(private configService: ConfigService) {}

  async createDeepgramKey(): Promise<{ key: string }> {
    const apiKey = this.configService.get<string>('DEEPGRAM_API_KEY');
    const projectId = this.configService.get<string>('DEEPGRAM_PROJECT_ID');

    if (!apiKey || !projectId) {
      throw new Error('Deepgram environment variables are missing.');
    }

    const response = await fetch(
      `https://api.deepgram.com/v1/projects/${projectId}/keys`,
      {
        method: 'POST',
        headers: {
          Authorization: `Token ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          comment: 'Temporary client key for SST',
          scopes: ['member'],
          time_to_live_in_seconds: 60,
        }),
      }
    );

    if (!response.ok) {
      const errorData = await response.json();
      console.error('Deepgram API Error:', errorData);
      throw new Error('Failed to create temporary key');
    }

    const data = await response.json();

    let keyValue: string | null = null;
    if (data) {
      if (typeof data.api_key === 'string') keyValue = data.api_key;
      else if (data.api_key?.api_key) keyValue = data.api_key.api_key;
      else if (data.key) keyValue = data.key;
      else if (data.apiKey) keyValue = data.apiKey;
      else if (data.api_key?.token) keyValue = data.api_key.token;
    }

    if (!keyValue) {
      console.error('Deepgram returned unexpected payload:', data);
      throw new Error('Deepgram did not return a usable temporary key');
    }

    return { key: keyValue };
  }
}