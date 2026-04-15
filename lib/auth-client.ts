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
  fetchOptions: {
    onError(e: any) {
      if (e.error?.status === 429) {
        console.warn("Rate limited! Too many requests.");
        if (typeof window !== "undefined") {
          alert("Too many requests. Please try again in a minute.");
        }
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

