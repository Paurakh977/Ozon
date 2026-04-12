import { betterAuth } from "better-auth";
import { prismaAdapter } from "better-auth/adapters/prisma";
import { twoFactor } from "better-auth/plugins/two-factor";
import { admin } from "better-auth/plugins/admin";
import { PrismaClient } from "@prisma/client";
import { sendEmail } from "./email";

const prisma = new PrismaClient();

export const auth: any = betterAuth({
  appName: "MyApp",

  database: prismaAdapter(prisma, {
    provider: "postgresql",
  }),

  // ─── Email & Password ───────────────────────────────────────────────────────
  emailAndPassword: {
    enabled: true,
    minPasswordLength: 8,
    maxPasswordLength: 128,
    requireEmailVerification: true,

    sendResetPassword: async ({ user, url }) => {
      await sendEmail({
        to: user.email,
        subject: "Reset your password — MyApp",
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

  // ─── Email Verification ─────────────────────────────────────────────────────
  emailVerification: {
    sendVerificationEmail: async ({ user, url }) => {
      await sendEmail({
        to: user.email,
        subject: "Verify your email — MyApp",
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
      });
    },
    // Redirect here after clicking the email link
    callbackURL: "http://localhost:3000/auth/verify-email",
  },

  // ─── Social Providers ───────────────────────────────────────────────────────
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

  // ─── Session ────────────────────────────────────────────────────────────────
  session: {
    expiresIn: 60 * 60 * 24 * 7,
    updateAge: 60 * 60 * 24,
    cookieCache: {
      enabled: true,
      maxAge: 60 * 5,
    },
  },

  // ─── Rate Limiting ──────────────────────────────────────────────────────────
  rateLimit: {
    enabled: true,
    window: 60,
    max: 20,
    storage: "database",
  },

  trustedOrigins: [
    "http://localhost:3000",
    "https://yourdomain.com",
  ],

  advanced: {
    useSecureCookies: false,
    // Fix the IP warning from your logs:
    ipAddress: {
      ipAddressHeaders: ["x-forwarded-for", "x-real-ip"],
    },
  },

  plugins: [
    twoFactor({
      issuer: "MyApp",
      totpOptions: {
        digits: 6,
        period: 30,
      },
      // ── Email OTP (this fixes "send otp isn't configured") ──────────────────
      otpOptions: {
        sendOTP: async ({ user, otp }) => {
          await sendEmail({
            to: user.email,
            subject: "Your verification code — MyApp",
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
          });
        },
        period: 3,           // expires in 3 minutes
        allowedAttempts: 5,
      },
      backupCodeOptions: {
        amount: 10,
        length: 10,
        storeBackupCodes: "encrypted",
      },
      twoFactorCookieMaxAge: 600,
      trustDeviceMaxAge: 60 * 60 * 24 * 30,
    }),

    admin(),
  ],

  hooks: {},
});

export type Auth = typeof auth;