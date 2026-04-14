import 'dotenv/config';

import { NestFactory } from '@nestjs/core';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AppModule } from './app.module';
import { ValidationPipe, Logger } from '@nestjs/common';
import helmet from 'helmet';
import compression from 'compression';

async function bootstrap() {
  const logger = new Logger('Bootstrap');

  const requiredEnvVars = [
    'PORT',
    'DATABASE_URL',
    'BETTER_AUTH_SECRET',
    'BETTER_AUTH_URL',
    'NEXT_PUBLIC_APP_URL',
    'GOOGLE_CLIENT_ID',
    'GOOGLE_CLIENT_SECRET',
    'GITHUB_CLIENT_ID',
    'GITHUB_CLIENT_SECRET',
    'RESEND_API_KEY',
    'REDIS_URL',
  ];
  for (const key of requiredEnvVars) {
    if (!process.env[key]) {
      throw new Error(`Missing required environment variable: ${key}`);
    }
  }

  // ✅ Type as NestExpressApplication to access Express-specific methods
  const app = await NestFactory.create<NestExpressApplication>(AppModule, {
    bodyParser: false,
  });

  // Trust nginx reverse proxy — fixes rate limit IP warning
  app.set('trust proxy', 1);

  // ✅ Security headers via Helmet — tuned for a JSON API server.
  // CSP is intentionally omitted: it is only meaningful for HTML pages,
  // not JSON API responses, and it can break browser preflight handling.
  app.use(
    helmet({
      // CSP off — this is a pure API server, not serving HTML
      contentSecurityPolicy: false,

      // CORP must be cross-origin so browser-side JS can read our JSON responses.
      // (default is 'same-origin' which blocks cross-origin fetch reads)
      crossOriginResourcePolicy: { policy: 'cross-origin' },

      // COEP off — required so OAuth redirect flows work in-browser
      crossOriginEmbedderPolicy: false,

      // COOP off — OAuth popups need to communicate back to opener
      crossOriginOpenerPolicy: false,

      // X-Frame-Options: DENY — APIs should never be framed
      frameguard: { action: 'deny' },

      // X-Content-Type-Options: nosniff
      noSniff: true,

      // HSTS — production only (nginx already sends this in dev,
      // and Node behind nginx should not re-send to avoid double-header)
      strictTransportSecurity:
        process.env.NODE_ENV === 'production'
          ? { maxAge: 31536000, includeSubDomains: true }
          : false,

      // Referrer-Policy
      referrerPolicy: { policy: 'strict-origin-when-cross-origin' },

      xssFilter: false,
      permittedCrossDomainPolicies: { permittedPolicies: 'none' },
    }),
  );

  // ✅ Response compression (gzip/br)
  app.use(compression());

  app.setGlobalPrefix('api', {
    exclude: ['auth/*path'],
  });

  app.useGlobalPipes(
    new ValidationPipe({
      transform: true,
      whitelist: true,
      forbidNonWhitelisted: true,
    }),
  );

  // Build an explicit origin whitelist from config + well-known local dev origins.
  // Using a function (not a string) allows multiple origins with credentials.
  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? '';
  const allowedOrigins = new Set(
    [
      appUrl,
      // Local dev: Next.js dev server
      'http://localhost:3000',
      // Local dev: via nginx HTTPS (self-signed cert)
      'https://localhost',
      // Local dev: via nginx HTTP (before redirect) — kept for completeness
      'http://localhost',
    ].filter(Boolean),
  );

  app.enableCors({
    origin: (origin, callback) => {
      // Allow server-to-server calls (no Origin header) and whitelisted origins
      if (!origin || allowedOrigins.has(origin)) {
        callback(null, true);
      } else {
        callback(new Error(`CORS: origin "${origin}" not allowed`));
      }
    },
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    credentials: true,
    allowedHeaders: [
      'Content-Type',
      'Authorization',
      'X-Requested-With',
      'cookie',
    ],
  });

  app.enableShutdownHooks();

  await app.listen(process.env.PORT!);
  logger.log(`Microservice running on ${process.env.BETTER_AUTH_URL}`);
  logger.log(`CORS allowed origins: ${[...allowedOrigins].join(', ')}`);
}

bootstrap();