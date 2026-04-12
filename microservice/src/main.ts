import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { ValidationPipe, Logger } from '@nestjs/common';

async function bootstrap() {
  const logger = new Logger('Bootstrap');

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
  if (!allowedOrigin) {
    throw new Error('NEXT_PUBLIC_APP_URL environment variable is required');
  }

  app.enableCors({
    origin: allowedOrigin,
    methods: ['GET', 'POST', 'OPTIONS'],
    credentials: true,
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'cookie'],
  });

  app.enableShutdownHooks();

  const port = process.env.PORT;
  if (!port) {
    throw new Error('PORT environment variable is required');
  }

  await app.listen(port);
  logger.log(`Microservice running on http://localhost:${port}`);
}

bootstrap();