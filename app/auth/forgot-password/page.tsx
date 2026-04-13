// app/auth/forgot-password/page.tsx
"use client";

import { useState } from "react";
import { authClient } from "@/lib/auth-client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const { error } = await authClient.requestPasswordReset({
      email,
      redirectTo: `${APP_URL}/auth/reset-password`,
    });
    if (error) setError(error.message ?? "Something went wrong");
    else setSent(true);
  };

  if (sent) {
    return (
      <div style={centerStyle}>
        <div style={cardStyle}>
          <h2>Check your email</h2>
          <p>If an account exists for {email}, you will receive a reset link shortly.</p>
          <a href="/auth" style={{ color: "#6366f1" }}>Back to sign in</a>
        </div>
      </div>
    );
  }

  return (
    <div style={centerStyle}>
      <div style={cardStyle}>
        <h2>Reset Password</h2>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <input
            type="email"
            placeholder="Your email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={{ padding: "12px", border: "1px solid #e2e8f0", borderRadius: "8px" }}
          />
          {error && <p style={{ color: "#ef4444", fontSize: "13px" }}>{error}</p>}
          <button type="submit" style={{ padding: "12px", background: "#6366f1", color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer" }}>
            Send reset link
          </button>
        </form>
      </div>
    </div>
  );
}

const centerStyle: React.CSSProperties = { minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" };
const cardStyle: React.CSSProperties = { background: "#fff", borderRadius: "12px", padding: "40px", maxWidth: "400px", width: "100%", boxShadow: "0 4px 24px rgba(0,0,0,0.08)" };