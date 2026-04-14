import { Test, TestingModule } from '@nestjs/testing';
import { RatelimitController } from './ratelimit.controller';
import { RateLimitService } from './ratelimit.service';
import { ConfigService } from '@nestjs/config';
import { REDIS_CLIENT } from '../redis/redis.module';

const mockRedis = {
  eval: jest.fn().mockResolvedValue(1),
  on: jest.fn(),
};

const mockRateLimitService = {
  check: jest.fn().mockResolvedValue(true),
};

describe('RatelimitController', () => {
  let controller: RatelimitController;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [RatelimitController],
      providers: [
        { provide: RateLimitService, useValue: mockRateLimitService },
        { provide: REDIS_CLIENT, useValue: mockRedis },
        { provide: ConfigService, useValue: { get: jest.fn().mockReturnValue(6) } },
      ],
    }).compile();

    controller = module.get<RatelimitController>(RatelimitController);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  it('health() should return { status: "ok" }', () => {
    expect(controller.health()).toEqual({ status: 'ok' });
  });
});
