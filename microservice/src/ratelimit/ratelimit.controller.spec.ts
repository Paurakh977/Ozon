import { Test, TestingModule } from '@nestjs/testing';
import { RatelimitController } from './ratelimit.controller';
import { RateLimitService } from './ratelimit.service';

describe('RatelimitController', () => {
  let controller: RatelimitController;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [RatelimitController],
      providers: [RateLimitService],
    }).compile();

    controller = module.get<RatelimitController>(RatelimitController);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });
});
