import { NextResponse } from 'next/server';

export async function GET(req: Request) {
  const apiKey = process.env.DEEPGRAM_API_KEY;
  const projectId = process.env.DEEPGRAM_PROJECT_ID;
  // Basic in-process rate limiting to reduce abuse before auth/rate-limiting is added.
  // Note: in serverless / multi-instance deployments this is best-effort only.
  const MAX_KEYS_PER_WINDOW = parseInt(process.env.SST_MAX_KEYS_PER_WINDOW || '6', 10);
  const WINDOW_MS = parseInt(process.env.SST_KEY_WINDOW_MS || String(60 * 1000), 10);

  if (!apiKey || !projectId) {
    return NextResponse.json(
      { error: 'Deepgram environment variables are missing.' },
      { status: 500 }
    );
  }

  // Simple origin check (optional): set SST_ALLOWED_ORIGIN or NEXT_PUBLIC_APP_URL to restrict.
  const allowedOrigin = process.env.SST_ALLOWED_ORIGIN || process.env.NEXT_PUBLIC_APP_URL || null;
  const origin = req.headers.get('origin') || req.headers.get('referer') || '';
  if (allowedOrigin && origin && !origin.includes(allowedOrigin)) {
    console.warn('Blocked key request from disallowed origin:', origin);
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  // Identify client IP (best-effort). Prefer X-Forwarded-For when behind a proxy.
  const forwarded = req.headers.get('x-forwarded-for') || '';
  const ip = (forwarded.split(',')[0] || req.headers.get('x-real-ip') || 'unknown').trim();

  // In-memory rate limiter map on the global object (best-effort).
  // This prevents a single IP from requesting unlimited keys quickly.
  // For production, replace with a centralized store (Redis) and proper auth.
  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-ignore
  if (!globalThis.__dg_sst_rate_map) globalThis.__dg_sst_rate_map = new Map();
  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-ignore
  const rateMap: Map<string, number[]> = globalThis.__dg_sst_rate_map;
  const now = Date.now();
  const windowKey = `sst:${ip}`;
  const recent = (rateMap.get(windowKey) || []).filter((t) => now - t < WINDOW_MS);
  if (recent.length >= MAX_KEYS_PER_WINDOW) {
    console.warn(`Rate limit exceeded for IP ${ip}`);
    return NextResponse.json({ error: 'Rate limit exceeded' }, { status: 429 });
  }
  recent.push(now);
  rateMap.set(windowKey, recent);

  try {
    const response = await fetch(`https://api.deepgram.com/v1/projects/${projectId}/keys`, {
      method: 'POST',
      headers: {
        'Authorization': `Token ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        comment: 'Temporary client key for SST',
        scopes: ['member'],
        time_to_live_in_seconds: 60 // Key automatically self-destructs in 60s
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      // Log details server-side for debugging but do not expose them to clients
      console.error('Deepgram API Error:', errorData);
      return NextResponse.json(
        { error: 'Failed to create temporary key' },
        { status: response.status }
      );
    }

    const data = await response.json();
    
    // Extract key from Deepgram response (handle nested shapes)
    let keyValue: string | null = null;
    if (data) {
      if (typeof data.api_key === 'string') keyValue = data.api_key;
      else if (data.api_key && typeof data.api_key.api_key === 'string') keyValue = data.api_key.api_key;
      else if (data.key && typeof data.key === 'string') keyValue = data.key;
      else if ((data as any).apiKey && typeof (data as any).apiKey === 'string') keyValue = (data as any).apiKey;
      else if (data.api_key && typeof data.api_key.token === 'string') keyValue = data.api_key.token;
    }

    if (!keyValue) {
      // Keep the payload private; log it server-side for investigation
      console.error('Deepgram returned unexpected payload when creating key:', data);
      return NextResponse.json({ error: 'Deepgram did not return a usable temporary key' }, { status: 500 });
    }

    // Safely return the short-lived key
    return NextResponse.json({ key: keyValue });
  } catch (error) {
    console.error('Network error generating Deepgram key:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}