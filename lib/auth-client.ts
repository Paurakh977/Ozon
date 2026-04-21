// lib/auth-client.ts
import { createAuthClient } from "better-auth/react";
import { twoFactorClient } from "better-auth/client/plugins";
import { jwtClient } from "better-auth/client/plugins";

type AuthClientError = { error?: { status?: number } };

let lastRateLimitWarnAt = 0;

function notifyRateLimit() {
  const now = Date.now();
  // Prevent noisy repeated logs when multiple background auth calls hit 429.
  if (now - lastRateLimitWarnAt < 5000) return;
  lastRateLimitWarnAt = now;
  console.warn("Rate limited! Too many requests.");
}
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
    jwtClient(), 
  ],
  fetchOptions: {
    credentials: "include",
    onError(e: AuthClientError) {
      if (e.error?.status === 429) {
        notifyRateLimit();
        // We can throw an error or just let it pass so it doesn't trigger a global logout
        // The individual hooks will just return an error state instead of null data that causes redirects.
      }
    },
  },
});

export const {
  signIn,
  signUp,
  signOut,
  useSession,
  getSession,
} = authClient;

