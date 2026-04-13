// lib/auth-client.ts
import { createAuthClient } from "better-auth/react";
import { twoFactorClient } from "better-auth/client/plugins";

/**
 * NEXT_PUBLIC_API_URL: Your NestJS API server base URL
 * 
 * This MUST be the same as BETTER_AUTH_URL in your NestJS .env file.
 * - In DEVELOPMENT: http://localhost:3001
 * - In PRODUCTION: https://api.yourdomain.com
 * 
 * This tells the client where to make authentication API calls.
 * Used for: signIn, signUp, signOut, session management, OAuth flows.
 */
export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_API_URL as string,
  plugins: [
    twoFactorClient({
      onTwoFactorRedirect() {
        window.location.href = "/auth/two-factor";
      },
    }),
  ],
});

export const {
  signIn,
  signUp,
  signOut,
  useSession,
  getSession,
} = authClient;
