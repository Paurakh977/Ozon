import { betterAuth } from "better-auth";
import { prismaAdapter } from "better-auth/adapters/prisma";
import { twoFactor } from "better-auth/plugins/two-factor";
import { admin } from "better-auth/plugins/admin";
import { PrismaClient } from "@prisma/client";
import { sendEmail } from "./email";
import Redis from "ioredis";
import { jwt } from "better-auth/plugins";

const redis = new Redis(process.env.REDIS_URL || "");

const prisma = new PrismaClient({
  log: ['query', 'info', 'warn', 'error'], // <-- Enabled Prisma query logging
});

const API_URL = process.env.BETTER_AUTH_URL as string;
const APP_URL = process.env.NEXT_PUBLIC_APP_URL as string;


export const auth: any = betterAuth({
  appName: "Ozon",

  secondaryStorage: {
    get: async (key) => {
      const value = await redis.get(key);
      const isRL = key.includes("rate-limit") || key.includes("rl:") || key.includes("|");
      const prefix = isRL ? "🛡️ [RateLimit Redis]" : "📦 [Redis Cache]";
      console.log(`${prefix} GET ${key} -> ${value ? "🟢 HIT" : "🔴 MISS"}`);
      return value ? value : null;
    },
    set: async (key, value, ttl) => {
      const isRL = key.includes("rate-limit") || key.includes("rl:") || key.includes("|");
      const prefix = isRL ? "🛡️ [RateLimit Redis]" : "📦 [Redis Cache]";
      const ttlMsg = ttl ? `(TTL: ${ttl}s)` : "";
      console.log(`${prefix} SET ${key} ${ttlMsg}`);
      if (ttl) await redis.set(key, value, "EX", ttl);
      else await redis.set(key, value);
    },
    delete: async (key) => {
      const isRL = key.includes("rate-limit") || key.includes("rl:") || key.includes("|");
      const prefix = isRL ? "🛡️ [RateLimit Redis]" : "📦 [Redis Cache]";
      console.log(`${prefix} DELETE ${key}`);
      await redis.del(key);
    },
  },

  database: prismaAdapter(prisma, {
    provider: "postgresql",
  }),

  emailAndPassword: {
    enabled: true,
    minPasswordLength: 8,
    maxPasswordLength: 128,
    requireEmailVerification: true,

    sendResetPassword: async ({ user, url }) => {
      // Fire and forget email sending to prevent timing attacks
      sendEmail({
        to: user.email,
        subject: "Reset your password — Ozon",
        html: `
          <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px">
            <h2 style="color:#1e293b">Reset your password</h2>
            <p style="color:#64748b">Click the button below to set a new password for your account.</p>
            <a href="${url}"
               style="display:inline-block;padding:12px 24px;background:#6366f1;color:#fff;
                      border-radius:8px;text-decoration:none;font-weight:600;margin:16px 0">
              Reset Password
            </a>
            <p style="color:#94a3b8;font-size:12px">
              This link expires in 1 hour. If you didn't request this, ignore this email.
            </p>
          </div>
        `,
      });
    },

    revokeSessionsOnPasswordReset: true,
  },

  emailVerification: {
    sendVerificationEmail: async ({ user, url }) => {
      // Fire and forget email sending to prevent timing attacks
      sendEmail({
        to: user.email,
        subject: "Verify your email — Ozon",
        html: `
          <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px">
            <h2 style="color:#1e293b">Verify your email</h2>
            <p style="color:#64748b">Click below to verify your email and activate your account.</p>
            <a href="${url}"
              style="display:inline-block;padding:12px 24px;background:#6366f1;color:#fff;
                      border-radius:8px;text-decoration:none;font-weight:600;margin:16px 0">
              Verify Email
            </a>
            <p style="color:#94a3b8;font-size:12px">
              This link expires in 24 hours. If you didn't sign up, ignore this email.
            </p>
          </div>
        `,
      }); // .catch() removed since sendEmail handles or ignores its own rejects or returns void
    },
    callbackURL: `${APP_URL}/auth/verify-email`,
  },

  socialProviders: {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID as string,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET as string,
      prompt: "select_account",
    },
    github: {
      clientId: process.env.GITHUB_CLIENT_ID as string,
      clientSecret: process.env.GITHUB_CLIENT_SECRET as string,
    },
  },

  session: {
    storeSessionInDatabase: true,
    expiresIn: process.env.SESSION_EXPIRES_IN ? parseInt(process.env.SESSION_EXPIRES_IN) : 60 * 60 * 24 * 7,
    updateAge: process.env.SESSION_UPDATE_AGE ? parseInt(process.env.SESSION_UPDATE_AGE) : 60 * 60 * 24,
    cookieCache: {
      enabled: true,
      maxAge: process.env.SESSION_COOKIE_MAX_AGE ? parseInt(process.env.SESSION_COOKIE_MAX_AGE) : 60 * 5,
    },
  },

  rateLimit: {
    enabled: true,
    window: process.env.RATE_LIMIT_WINDOW ? parseInt(process.env.RATE_LIMIT_WINDOW) : 60,
    max: process.env.RATE_LIMIT_MAX ? parseInt(process.env.RATE_LIMIT_MAX) : 20,
    storage: "secondary-storage",
    customRules: {
      "/api/auth/sign-in/email": { window: 60, max: 5 }, // strict login limit
      "/api/auth/sign-up/email": { window: 60, max: 3 }, // strict signup limit
      "/api/auth/forget-password": { window: 60, max: 3 }
    }
  },

  trustedOrigins: [
    "http://localhost:3000",
    APP_URL,
    "https://localhost"
  ],

  advanced: {
    useSecureCookies: process.env.BETTER_AUTH_URL?.startsWith("https") ?? false,
    ipAddress: {
      disableIpTracking: false, 
      ipAddressHeaders: ["x-forwarded-for", "x-real-ip"],
    },
    backgroundTasks: {
      handler: async (promise) => {
        try {
          await promise;
        } catch (e) {
          console.error("Better Auth Background Task Failed:", e);
        }
      },
    },
  },

  plugins: [
    twoFactor({
      issuer: "Ozon",
      totpOptions: {
        digits: 6,
        period: process.env.TWO_FACTOR_TOTP_PERIOD ? parseInt(process.env.TWO_FACTOR_TOTP_PERIOD) : 30, // 30secs
      },
      otpOptions: {
        sendOTP: async ({ user, otp }) => {
          // Fire and forget OTP email to prevent timing attacks
          sendEmail({
            to: user.email,
            subject: "Your verification code — Ozon",
            html: `
              <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px">
                <h2 style="color:#1e293b">Your verification code</h2>
                <p style="color:#64748b">Use this code to complete sign-in. It expires in 3 minutes.</p>
                <div style="font-size:36px;font-weight:700;letter-spacing:8px;
                            color:#6366f1;padding:16px 0">
                  ${otp}
                </div>
                <p style="color:#94a3b8;font-size:12px">
                  If you didn't request this code, ignore this email.
                </p>
              </div>
            `,
          }); // removed await
        },
        period: process.env.TWO_FACTOR_OTP_PERIOD ? parseInt(process.env.TWO_FACTOR_OTP_PERIOD) : 3, // 3mins
        allowedAttempts: process.env.TWO_FACTOR_OTP_ATTEMPTS ? parseInt(process.env.TWO_FACTOR_OTP_ATTEMPTS) : 5,
      },
      backupCodeOptions: {
        amount: process.env.TWO_FACTOR_BACKUP_AMOUNT ? parseInt(process.env.TWO_FACTOR_BACKUP_AMOUNT) : 10,
        length: process.env.TWO_FACTOR_BACKUP_LENGTH ? parseInt(process.env.TWO_FACTOR_BACKUP_LENGTH) : 10,
        storeBackupCodes: "encrypted",
      },
      twoFactorCookieMaxAge: process.env.TWO_FACTOR_COOKIE_MAX_AGE ? parseInt(process.env.TWO_FACTOR_COOKIE_MAX_AGE) : 600,
      trustDeviceMaxAge: process.env.TRUST_DEVICE_MAX_AGE ? parseInt(process.env.TRUST_DEVICE_MAX_AGE) : 60 * 60 * 24 * 30,
    }),

    admin(),

    jwt({
      jwt: {
        // ES256 has the best cross-language support (Python, Go, etc.)
        // EdDSA (default) is poorly supported in python-jose
        expirationTime: "30m",

        // Only embed what FastAPI actually needs — keep payload lean
        definePayload: ({ user }) => ({
          sub:   user.id,
          email: user.email,
          // Add role/plan here if you have it, e.g.: plan: user.plan
        }),

        issuer:   API_URL,   // e.g. "https://api.yourdomain.com"
        audience: API_URL,
      },
      jwks: {
        keyPairConfig: {
          alg: "ES256",      // ← override the default EdDSA
        },
        rotationInterval: 60 * 60 * 24 * 30, // rotate keys every 30 days
        gracePeriod:      60 * 60 * 24 * 7,  // old key valid 7 days after rotation
      },
    }),
    
  ],

  hooks: {},
});

export type Auth = typeof auth;
