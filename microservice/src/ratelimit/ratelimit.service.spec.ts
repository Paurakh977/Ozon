import { Test, TestingModule } from '@nestjs/testing';
import { RateLimitService } from './ratelimit.service';
import { ConfigService } from '@nestjs/config';
import { REDIS_CLIENT } from '../redis/redis.module';

const mockRedis = {
  eval: jest.fn(),
  on: jest.fn(),
};

describe('RateLimitService', () => {
  let service: RateLimitService;

  beforeEach(async () => {
    mockRedis.eval.mockResolvedValue(1); // allow by default

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        RateLimitService,
        {
          provide: REDIS_CLIENT,
          useValue: mockRedis,
        },
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string, defaultVal: number) => {
              if (key === 'SST_MAX_KEYS_PER_WINDOW') return 3;
              if (key === 'SST_KEY_WINDOW_MS') return 60_000;
              return defaultVal;
            }),
          },
        },
      ],
    }).compile();

    service = module.get<RateLimitService>(RateLimitService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('check() returns true when Redis allows', async () => {
    mockRedis.eval.mockResolvedValue(1);
    await expect(service.check('user-123', 'stt')).resolves.toBe(true);
  });

  it('check() returns false when Redis denies (rate exceeded)', async () => {
    mockRedis.eval.mockResolvedValue(0);
    await expect(service.check('user-123', 'stt')).resolves.toBe(false);
  });

  it('check() fails open (returns true) on Redis error', async () => {
    mockRedis.eval.mockRejectedValue(new Error('Redis connection lost'));
    await expect(service.check('user-123', 'stt')).resolves.toBe(true);
  });
});
