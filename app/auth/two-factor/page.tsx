// app/auth/two-factor/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authClient } from "@/lib/auth-client";

type Method = "totp" | "otp" | "backup";

export default function TwoFactorPage() {
  const router = useRouter();
  const [method, setMethod] = useState<Method>("totp");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [trustDevice, setTrustDevice] = useState(false);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    let result;

    if (method === "totp") {
      result = await authClient.twoFactor.verifyTotp({ code, trustDevice });
    } else if (method === "otp") {
      result = await authClient.twoFactor.verifyOtp({ code, trustDevice });
    } else {
      result = await authClient.twoFactor.verifyBackupCode({ code, trustDevice });
    }

    if (result.error) {
      setError(result.error.message ?? "Invalid code. Please try again.");
    } else {
      router.push("/dashboard");
    }

    setLoading(false);
  };

  const sendOtp = async () => {
    await authClient.twoFactor.sendOtp();
    alert("OTP sent to your email!");
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>Two-Factor Authentication</h1>
        <p style={styles.subtitle}>Verify your identity to continue</p>

        {/* Method selector */}
        <div style={styles.methodRow}>
          {(["totp", "otp", "backup"] as Method[]).map((m) => (
            <button
              key={m}
              onClick={() => setMethod(m)}
              style={{
                ...styles.methodBtn,
                ...(method === m ? styles.methodBtnActive : {}),
              }}
            >
              {m === "totp" ? "Authenticator" : m === "otp" ? "Email OTP" : "Backup Code"}
            </button>
          ))}
        </div>

        <form onSubmit={handleVerify} style={styles.form}>
          {method === "totp" && (
            <p style={styles.hint}>Enter the 6-digit code from your authenticator app</p>
          )}
          {method === "otp" && (
            <div>
              <p style={styles.hint}>Enter the code sent to your email</p>
              <button type="button" onClick={sendOtp} style={styles.secondaryBtn}>
                Send OTP
              </button>
            </div>
          )}
          {method === "backup" && (
            <p style={styles.hint}>Enter one of your saved backup codes</p>
          )}

          <input
            style={styles.input}
            type="text"
            placeholder={method === "backup" ? "Backup code" : "000000"}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={method === "backup" ? 20 : 6}
            required
            autoComplete="one-time-code"
          />

          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={trustDevice}
              onChange={(e) => setTrustDevice(e.target.checked)}
            />
            {" "}Trust this device for 30 days
          </label>

          {error && <p style={styles.error}>{error}</p>}

          <button type="submit" style={styles.primaryBtn} disabled={loading}>
            {loading ? "Verifying..." : "Verify"}
          </button>
        </form>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: "100vh", display: "flex", alignItems: "center",
    justifyContent: "center", background: "#f8fafc",
  },
  card: {
    background: "#fff", borderRadius: "12px", padding: "40px",
    width: "100%", maxWidth: "400px", boxShadow: "0 4px 24px rgba(0,0,0,0.08)",
  },
  title: { fontSize: "22px", fontWeight: 700, color: "#1e293b", marginBottom: "8px" },
  subtitle: { color: "#64748b", fontSize: "14px", marginBottom: "24px" },
  methodRow: { display: "flex", gap: "8px", marginBottom: "20px" },
  methodBtn: {
    flex: 1, padding: "8px", border: "1px solid #e2e8f0",
    borderRadius: "6px", background: "#fff", cursor: "pointer", fontSize: "12px",
  },
  methodBtnActive: { background: "#6366f1", color: "#fff", borderColor: "#6366f1" },
  form: { display: "flex", flexDirection: "column", gap: "12px" },
  hint: { color: "#64748b", fontSize: "13px", margin: "0" },
  input: {
    padding: "12px 14px", border: "1px solid #e2e8f0", borderRadius: "8px",
    fontSize: "16px", outline: "none", letterSpacing: "4px", textAlign: "center",
    width: "100%", boxSizing: "border-box",
  },
  checkboxLabel: { fontSize: "13px", color: "#64748b", display: "flex", alignItems: "center", gap: "6px" },
  primaryBtn: {
    padding: "12px", background: "#6366f1", color: "#fff", border: "none",
    borderRadius: "8px", cursor: "pointer", fontSize: "15px", fontWeight: 600,
  },
  secondaryBtn: {
    padding: "8px 14px", background: "#f1f5f9", border: "1px solid #e2e8f0",
    borderRadius: "6px", cursor: "pointer", fontSize: "13px",
  },
  error: { color: "#ef4444", fontSize: "13px", margin: "0" },
};