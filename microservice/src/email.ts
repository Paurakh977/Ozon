// src/email.ts
import { Resend } from "resend";

const resend = new Resend(process.env.RESEND_API_KEY);

// DEV: Resend free tier only allows sending to your own account email.
// Set this to the email you signed up to Resend with.
// In production with a verified domain, remove DEV_EMAIL_OVERRIDE.
const DEV_EMAIL_OVERRIDE = process.env.DEV_EMAIL_OVERRIDE;

export async function sendEmail({
  to,
  subject,
  html,
}: {
  to: string;
  subject: string;
  html: string;
}) {
  const recipient = DEV_EMAIL_OVERRIDE ?? to;

  const { error } = await resend.emails.send({
    from: "Ozon <onboarding@resend.dev>",
    to: recipient,
    subject: DEV_EMAIL_OVERRIDE ? `[DEV → ${to}] ${subject}` : subject,
    html,
  });

  if (error) {
    console.error("[Email Error]", error);
    throw new Error(error.message);
  }

  if (DEV_EMAIL_OVERRIDE) {
    console.log(`[Email] Redirected from ${to} → ${recipient} | Subject: ${subject}`);
  }
}