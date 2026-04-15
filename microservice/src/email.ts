// src/email.ts
import { Resend } from "resend";

const resend = new Resend(process.env.RESEND_API_KEY);

/**
 * DEV_EMAIL_OVERRIDE: In development (Resend free tier), emails can only be sent
 * to your own verified email. Set this to redirect all emails to your email.
 * 
 * In PRODUCTION: Remove this env var entirely to send to real user emails.
 * Also update the "from" address below to use your verified domain.
 */
const DEV_EMAIL_OVERRIDE = process.env.DEV_EMAIL_OVERRIDE;

/**
 * BETTER_AUTH_URL: The API server URL used in email links.
 * In PRODUCTION: https://api.yourdomain.com
 */
const API_URL = process.env.BETTER_AUTH_URL as string;

/**
 * NEXT_PUBLIC_APP_URL: Your frontend URL for email callbacks.
 * In PRODUCTION: https://yourdomain.com
 */
const APP_URL = process.env.NEXT_PUBLIC_APP_URL as string;

const isProduction = process.env.NODE_ENV === "production";

/**
 * Send an email using Resend.
 * 
 * In production with a verified domain:
 * - Update the "from" address to: "Ozon <noreply@yourdomain.com>"
 * - Remove DEV_EMAIL_OVERRIDE from environment
 */
export async function sendEmail({
  to,
  subject,
  html,
}: {
  to: string;
  subject: string;
  html: string;
}): Promise<void> {
  const recipient = DEV_EMAIL_OVERRIDE ?? to;

  // In production, use your verified domain. In dev, use Resend's test domain.
  const fromAddress = DEV_EMAIL_OVERRIDE 
    ? "Ozon <onboarding@resend.dev>"
    : "Ozon <noreply@yourdomain.com>"; // TODO: Replace with your verified domain

  const { error } = await resend.emails.send({
    from: fromAddress,
    to: recipient,
    subject: DEV_EMAIL_OVERRIDE ? `[DEV → ${to}] ${subject}` : subject,
    html,
  });

  if (error) {
    console.error("[Email Error]", error);
    // Don't throw the error, just log it, so that fire-and-forget callers don't crash
    return;
  }

  if (DEV_EMAIL_OVERRIDE) {
    console.log(`[Email] Redirected from ${to} → ${recipient} | Subject: ${subject}`);
  }
}