import { betterAuth } from "better-auth";
import Redis from "ioredis";

const redis = new Redis(process.env.REDIS_URL || "");

const auth = betterAuth({
  secondaryStorage: {
    get: async (key: string) => {
      const val = await redis.get(key);
      return val ? val : null;
    },
    set: async (key: string, value: string, ttl?: number) => {
      if (ttl) {
        await redis.set(key, value, "EX", ttl);
      } else {
        await redis.set(key, value);
      }
    },
    delete: async (key: string) => {
      await redis.del(key);
    },
  },
});
