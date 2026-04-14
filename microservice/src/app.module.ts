import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import * as Joi from 'joi';
import { ThrottlerModule, ThrottlerGuard } from '@nestjs/throttler';
import { APP_GUARD } from '@nestjs/core';
import { AuthModule } from '@thallesp/nestjs-better-auth';
import { auth } from './auth';
import { RedisModule } from './redis/redis.module';
import { UsersModule } from './users/users.module';
import { SttModule } from './stt/stt.module';
import { ParseModule } from './parse/parse.module';
import { RatelimitModule } from './ratelimit/ratelimit.module';

@Module({
  imports: [
    // ─── Config (global) ──────────────────────────────────────────────────────
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
      validationSchema: Joi.object({
        PORT: Joi.number().required(),
        NEXT_PUBLIC_APP_URL: Joi.string().uri().required(),
        DEEPGRAM_API_KEY: Joi.string().required(),
        DEEPGRAM_PROJECT_ID: Joi.string().required(),
        MISTRAL_API_KEY: Joi.string().required(),
        REDIS_URL: Joi.string().uri().required(),
        REDIS_PASSWORD: Joi.string().min(8).required(),
        SST_MAX_KEYS_PER_WINDOW: Joi.number().integer().min(1).default(6),
        SST_KEY_WINDOW_MS: Joi.number().integer().min(1000).default(60_000),
      }),
      validationOptions: { abortEarly: true },
    }),

    // ─── Redis (global singleton via @Global decorator) ───────────────────────
    RedisModule,

    // ─── NestJS built-in HTTP throttler (defence-in-depth layer) ─────────────
    // This sits on top of our own Redis sliding-window guard and catches traffic
    // bursts that slip through before a session is established (e.g. login spam).
    ThrottlerModule.forRoot([
      {
        // Generous outer limit: 200 req / 60 s per IP
        // Actual per-endpoint limits are tighter (RateLimitService).
        name: 'global',
        ttl: 60_000,
        limit: 200,
      },
    ]),

    // ─── Better Auth ──────────────────────────────────────────────────────────
    AuthModule.forRoot({
      auth,
      bodyParser: {
        json: { limit: '2mb' },
        urlencoded: { limit: '2mb', extended: true },
      },
      // Global AuthGuard is ON by default — every route requires auth
      // unless decorated with @AllowAnonymous() or @OptionalAuth()
    }),

    // ─── Feature modules ─────────────────────────────────────────────────────
    UsersModule,
    SttModule,
    ParseModule,
    RatelimitModule,
  ],

  providers: [
    // Register @nestjs/throttler's guard globally as a second layer of defence
    {
      provide: APP_GUARD,
      useClass: ThrottlerGuard,
    },
  ],
})
export class AppModule {}