// app/auth/reset-password/page.tsx
"use client";

import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authClient } from "@/lib/auth-client";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (!token) {
      setError("Invalid or missing reset token.");
      return;
    }

    setLoading(true);
    setError("");

    const { error } = await authClient.resetPassword({
      newPassword: password,
      token,
    });

    if (error) {
      setError(error.message ?? "Reset failed.");
    } else {
      alert("Password set! You can now enable 2FA.");
      router.push("/dashboard");
    }
    setLoading(false);
  };

  return (
    <div style={center}>
      <div style={card}>
        <h2 style={{ margin: "0 0 8px", color: "#1e293b" }}>Set Your Password</h2>
        <p style={{ color: "#64748b", fontSize: "14px", marginBottom: "24px" }}>
          Create a password to enable two-factor authentication on your account.
        </p>
        <form onSubmit={handleSubmit} style={form}>
          <input
            type="password"
            placeholder="New password (min 8 characters)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
            style={input}
          />
          <input
            type="password"
            placeholder="Confirm new password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            style={input}
          />
          {error && <p style={{ color: "#ef4444", fontSize: "13px", margin: 0 }}>{error}</p>}
          <button type="submit" disabled={loading} style={btn}>
            {loading ? "Setting password..." : "Set Password"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div style={center}>Loading...</div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}

const center: React.CSSProperties = {
  minHeight: "100vh", display: "flex",
  alignItems: "center", justifyContent: "center", background: "#f8fafc",
};
const card: React.CSSProperties = {
  background: "#fff", borderRadius: "12px", padding: "40px",
  maxWidth: "420px", width: "100%", boxShadow: "0 4px 24px rgba(0,0,0,0.08)",
};
const form: React.CSSProperties = { display: "flex", flexDirection: "column", gap: "12px" };
const input: React.CSSProperties = {
  padding: "12px 14px", border: "1px solid #e2e8f0", borderRadius: "8px",
  fontSize: "14px", outline: "none", width: "100%", boxSizing: "border-box",
};
const btn: React.CSSProperties = {
  padding: "12px", background: "#6366f1", color: "#fff", border: "none",
  borderRadius: "8px", cursor: "pointer", fontSize: "15px", fontWeight: 600,
};