import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { SttModule } from './stt/stt.module';
import { ParseModule } from './parse/parse.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
    }),
    SttModule,
    ParseModule,
  ],
})
export class AppModule {}