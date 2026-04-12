import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { ValidationPipe, Logger } from '@nestjs/common';

async function bootstrap() {
  const logger = new Logger('Bootstrap');

  const requiredEnvVars = [
    'BETTER_AUTH_URL',
    'NEXT_PUBLIC_APP_URL',
    'PORT',
  ];

  for (const key of requiredEnvVars) {
    if (!process.env[key]) {
      throw new Error(`Missing required environment variable: ${key}`);
    }
  }

  const app = await NestFactory.create(AppModule, {
    bodyParser: false,
  });

  app.setGlobalPrefix('api', {
    exclude: ['/api/auth/(.*)'],
  });

  app.useGlobalPipes(
    new ValidationPipe({
      transform: true,
      whitelist: true,
      forbidNonWhitelisted: true,
    }),
  );

  const allowedOrigin = process.env.NEXT_PUBLIC_APP_URL;
  const apiUrl = process.env.BETTER_AUTH_URL;

  app.enableCors({
    origin: allowedOrigin,
    methods: ['GET', 'POST', 'OPTIONS'],
    credentials: true,
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'cookie'],
  });

  app.enableShutdownHooks();

  await app.listen(process.env.PORT!);
  logger.log(`Microservice running on ${apiUrl}`);
  logger.log(`CORS allowed origin: ${allowedOrigin}`);
}

bootstrap();