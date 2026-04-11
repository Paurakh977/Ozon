import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import * as Joi from 'joi';
import { AuthModule } from '@thallesp/nestjs-better-auth';
import { auth } from './auth';
import { UsersModule } from './users/users.module';
import { SttModule } from './stt/stt.module';
import { ParseModule } from './parse/parse.module';
import { RatelimitModule } from './ratelimit/ratelimit.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
      // Validate 
      validationSchema: Joi.object({
        PORT: Joi.number().required(),
        NEXT_PUBLIC_APP_URL: Joi.string().uri().required(),
        DEEPGRAM_API_KEY: Joi.string().required(),
        DEEPGRAM_PROJECT_ID: Joi.string().required(),
        MISTRAL_API_KEY: Joi.string().required(),
        SST_MAX_KEYS_PER_WINDOW: Joi.number().integer().min(1).default(6),
        SST_KEY_WINDOW_MS: Joi.number().integer().min(1000).default(60_000),
      }),
      validationOptions: { abortEarly: true },
    }),
    AuthModule.forRoot({
      auth,
      bodyParser: {
        json: { limit: '2mb' },
        urlencoded: { limit: '2mb', extended: true },
      },
    }),
    UsersModule,
    SttModule,
    ParseModule,
    RatelimitModule,
  ],
})
export class AppModule {}