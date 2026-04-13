import 'dotenv/config';

import { NestFactory } from '@nestjs/core';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AppModule } from './app.module';
import { ValidationPipe, Logger } from '@nestjs/common';

async function bootstrap() {
  const logger = new Logger('Bootstrap');

  const requiredEnvVars = ['BETTER_AUTH_URL', 'NEXT_PUBLIC_APP_URL', 'PORT'];
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

  app.setGlobalPrefix('api', {
    exclude: ['auth/*path'], 
  });

  app.useGlobalPipes(new ValidationPipe({
    transform: true,
    whitelist: true,
    forbidNonWhitelisted: true,
  }));

  app.enableCors({
    origin: process.env.NEXT_PUBLIC_APP_URL,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    credentials: true,
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'cookie'],
  });

  app.enableShutdownHooks();

  await app.listen(process.env.PORT!);
  logger.log(`Microservice running on ${process.env.BETTER_AUTH_URL}`);
  logger.log(`CORS allowed origin: ${process.env.NEXT_PUBLIC_APP_URL}`);
}

bootstrap();