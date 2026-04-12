// app/auth/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authClient } from "@/lib/auth-client";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup" | "verify-email">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendSent, setResendSent] = useState(false);


  const handleResendVerification = async () => {
    setResendLoading(true);
    const { error } = await authClient.sendVerificationEmail({
      email,
      callbackURL: "http://localhost:3000/dashboard",
    });
    if (error) {
      setError(error.message ?? "Failed to resend.");
    } else {
      setResendSent(true);
    }
    setResendLoading(false);
  };

  
  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    if (mode === "signup") {
      const { error } = await authClient.signUp.email({
        email,
        password,
        name,
        callbackURL: "http://localhost:3000/dashboard",
      });
      if (error) {
        setError(error.message ?? "Sign up failed");
      } else {
        // ← Show verification notice instead of redirecting
        setMode("verify-email");
        setLoading(false);
        return;
      }
    } else {
      const { data, error } = await authClient.signIn.email(
        { email, password, callbackURL: "http://localhost:3000/dashboard" },
        {
          onSuccess(ctx) {
            if (ctx.data?.twoFactorRedirect) return; // twoFactorClient handles this
            router.push("/dashboard");
          },
        }
      );

      if (error) {
        // ← Handle unverified email specifically
        if (error.code === "EMAIL_NOT_VERIFIED") {
          setMode("verify-email");
          setLoading(false);
          return;
        }
        setError(error.message ?? "Sign in failed");
      }
    }
    setLoading(false);
};

  const handleGoogleSignIn = async () => {
    await authClient.signIn.social({
      provider: "google",
      callbackURL: "http://localhost:3000/dashboard",
    });
  };

  const handleGithubSignIn = async () => {
    await authClient.signIn.social({
      provider: "github",
      callbackURL: "http://localhost:3000/dashboard",
    });
  };

  if (mode === "verify-email") {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={{ textAlign: "center" }}>
            <div style={{
              width: "64px", height: "64px", borderRadius: "50%",
              background: "#ede9fe", display: "flex", alignItems: "center",
              justifyContent: "center", margin: "0 auto 20px", fontSize: "28px"
            }}>
              📧
            </div>

            <h2 style={{ color: "#1e293b", marginBottom: "8px" }}>
              Check your email
            </h2>
            <p style={{ color: "#64748b", fontSize: "14px", marginBottom: "24px" }}>
              We sent a verification link to <strong>{email}</strong>.
              Click the link to activate your account and sign in.
            </p>

            {resendSent ? (
              <p style={{ color: "#22c55e", fontSize: "14px" }}>
                ✅ Verification email resent!
              </p>
            ) : (
              <button
                onClick={handleResendVerification}
                disabled={resendLoading}
                style={{
                  padding: "10px 20px", background: "#fff",
                  border: "1px solid #e2e8f0", borderRadius: "8px",
                  cursor: "pointer", fontSize: "14px", marginBottom: "12px",
                }}
              >
                {resendLoading ? "Sending..." : "Resend verification email"}
              </button>
            )}

            {error && <p style={styles.error}>{error}</p>}

            <p style={{ marginTop: "16px" }}>
              <button
                style={styles.linkBtn}
                onClick={() => {
                  setMode("signin");
                  setError("");
                  setResendSent(false);
                }}
              >
                ← Back to sign in
              </button>
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>
          {mode === "signin" ? "Sign In" : "Create Account"}
        </h1>

        {/* Social Login Buttons */}
        <button onClick={handleGoogleSignIn} style={styles.socialBtn}>
          <GoogleIcon /> Continue with Google
        </button>
        <button onClick={handleGithubSignIn} style={styles.socialBtnDark}>
          <GithubIcon /> Continue with GitHub
        </button>

        <div style={styles.divider}>
          <span>or</span>
        </div>

        {/* Email/Password Form */}
        <form onSubmit={handleEmailAuth} style={styles.form}>
          {mode === "signup" && (
            <input
              style={styles.input}
              type="text"
              placeholder="Full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          )}
          <input
            style={styles.input}
            type="email"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            style={styles.input}
            type="password"
            placeholder="Password (min 8 characters)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />

          {error && <p style={styles.error}>{error}</p>}

          <button type="submit" style={styles.primaryBtn} disabled={loading}>
            {loading
              ? "Please wait..."
              : mode === "signin"
              ? "Sign In"
              : "Create Account"}
          </button>
        </form>

        <p style={styles.switchText}>
          {mode === "signin" ? "Don't have an account? " : "Already have an account? "}
          <button
            style={styles.linkBtn}
            onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
          >
            {mode === "signin" ? "Sign up" : "Sign in"}
          </button>
        </p>

        {mode === "signin" && (
          <p style={styles.switchText}>
            <a href="/auth/forgot-password" style={{ color: "#6366f1" }}>
              Forgot password?
            </a>
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Inline styles ────────────────────────────────────────────────────────────
const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: "100vh", display: "flex", alignItems: "center",
    justifyContent: "center", background: "#f8fafc", fontFamily: "system-ui, sans-serif",
  },
  card: {
    background: "#fff", borderRadius: "12px", padding: "40px",
    width: "100%", maxWidth: "420px", boxShadow: "0 4px 24px rgba(0,0,0,0.08)",
  },
  title: { fontSize: "24px", fontWeight: 700, marginBottom: "24px", textAlign: "center", color: "#1e293b" },
  socialBtn: {
    width: "100%", padding: "12px", border: "1px solid #e2e8f0",
    borderRadius: "8px", background: "#fff", cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
    gap: "8px", marginBottom: "10px", fontSize: "14px", fontWeight: 500,
  },
  socialBtnDark: {
    width: "100%", padding: "12px", border: "1px solid #1e293b",
    borderRadius: "8px", background: "#1e293b", color: "#fff", cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
    gap: "8px", marginBottom: "10px", fontSize: "14px", fontWeight: 500,
  },
  divider: {
    textAlign: "center", margin: "20px 0", color: "#94a3b8",
    display: "flex", alignItems: "center", gap: "12px",
  },
  form: { display: "flex", flexDirection: "column", gap: "12px" },
  input: {
    padding: "12px 14px", border: "1px solid #e2e8f0", borderRadius: "8px",
    fontSize: "14px", outline: "none", width: "100%", boxSizing: "border-box",
  },
  primaryBtn: {
    padding: "12px", background: "#6366f1", color: "#fff", border: "none",
    borderRadius: "8px", cursor: "pointer", fontSize: "15px", fontWeight: 600,
    marginTop: "4px",
  },
  error: { color: "#ef4444", fontSize: "13px", margin: "0" },
  switchText: { textAlign: "center", fontSize: "13px", color: "#64748b", marginTop: "16px" },
  linkBtn: {
    background: "none", border: "none", color: "#6366f1",
    cursor: "pointer", fontSize: "13px", fontWeight: 600,
  },
};

// ─── SVG Icons ────────────────────────────────────────────────────────────────
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  );
}

function GithubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
    </svg>
  );
}