// app/dashboard/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authClient } from "@/lib/auth-client";
import QRCode from "react-qr-code";
import React from "react";

export default function DashboardPage() {
  const router = useRouter();
  const { data: session, isPending, error: sessionError } = authClient.useSession();

  // 2FA setup state
  const [show2FASetup, setShow2FASetup] = useState(false);
  const [totpURI, setTotpURI] = useState("");
  const [backupCodes, setBackupCodes] = useState<any>([]);
  const [totpCode, setTotpCode] = useState("");
  const [setupPassword, setSetupPassword] = useState("");
  const [setupStep, setSetupStep] = useState<"password" | "qr" | "done">("password");

  // Account listing (used to detect whether a user has a local password/credential)
  const [userAccounts, setUserAccounts] = useState<any>([]);

  useEffect(() => {
    if (session) {
      authClient.listAccounts().then((response: any) => {
        setUserAccounts(response.data ?? []);
      });
    }
  }, [session]);

  // Check if user has a credential (email/password) account
  const hasPasswordAccount = userAccounts ? userAccounts.find((acc: any) => acc.providerId === "credential") : false;

  useEffect(() => {
    // Check if the reason we don't have a session is just a rate limit.
    // If it is a rate limit, don't kick them out.
    if (!isPending && !session && sessionError?.status !== 429) {
      router.push("/auth");
    }
  }, [session, isPending, router, sessionError]);

  if (isPending) return <div style={styles.loading}>Loading...</div>;
  if (!session && sessionError?.status === 429) return <div style={styles.loading}>Rate limited. Please wait a moment...</div>;
  if (!session) return null;

  const handleSignOut = async () => {
    await authClient.signOut();
    router.push("/auth");
  };

  const handleEnable2FA = async () => {
    const { data, error } = await authClient.twoFactor.enable({ password: setupPassword });
    if (error) {
      alert(error.message);
      return;
    }
    if (data) {
      setTotpURI(data.totpURI);
      setBackupCodes(data.backupCodes);
      setSetupStep("qr");
    }
  };

  const handleVerify2FA = async () => {
    const { error } = await authClient.twoFactor.verifyTotp({ code: totpCode });
    if (error) {
      alert("Invalid code, try again");
    } else {
      setSetupStep("done");
      setShow2FASetup(false);
      alert("2FA enabled successfully!");
    }
  };

  const handleDisable2FA = async () => {
    const password = prompt("Enter your password to disable 2FA:");
    if (!password) return;
    const { error } = await authClient.twoFactor.disable({ password });
    if (error) alert(error.message);
    else alert("2FA disabled.");
  };

  const handleSetPassword = async () => {
  if (!session?.user?.email) return;

  const { error } = await authClient.requestPasswordReset({
    email: session.user.email,
    redirectTo: `${process.env.NEXT_PUBLIC_APP_URL}/auth/reset-password`,
  });

  if (error) {
    alert(error.message ?? "Failed to send reset email.");
  } else {
    alert(`A password setup link has been sent to ${session.user.email}. Check your inbox!`);
  }
    };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.logo}>MyApp</h1>
        <button onClick={handleSignOut} style={styles.signOutBtn}>Sign out</button>
      </div>

      <div style={styles.content}>
        <div style={styles.welcomeCard}>
          <div style={styles.avatar}>
            {session.user.image ? (
              <img src={session.user.image} alt="avatar" style={styles.avatarImg} />
            ) : (
              <span style={styles.avatarInitial}>
                {(session.user.name ?? session.user.email)[0].toUpperCase()}
              </span>
            )}
          </div>
          <div>
            <h2 style={styles.userName}>{session.user.name}</h2>
            <p style={styles.userEmail}>{session.user.email}</p>
            <p style={styles.badge}>
              {session.user.emailVerified ? "✅ Email verified" : "⚠️ Email not verified"}
            </p>
          </div>
        </div>

        {/* Security Card */}
        <div style={styles.securityCard}>
          <h3 style={styles.sectionTitle}>🔐 Security</h3>

          {!hasPasswordAccount ? (
            // OAuth-only user — no password exists
            <div style={styles.oauthNotice}>
              <p style={{ margin: 0, fontSize: "14px", color: "#64748b" }}>
                You signed in with{" "}
                  <strong>
                    {userAccounts[0] && userAccounts[0].providerId === "google" ? "Google" : "GitHub"}
                  </strong>
                . Two-factor authentication is managed by your social provider.
                To enable app-level 2FA, first{" "}
                <button
                  style={styles.linkBtn}
                  onClick={handleSetPassword}
                >
                  set a password
                </button>{" "}
                for your account.
              </p>
            </div>
          ) : (
            <div style={styles.securityRow}>
              <div>
                <p style={styles.securityLabel}>Two-Factor Authentication</p>
                <p style={styles.securityValue}>
                  {(session.user as any).twoFactorEnabled ? "Enabled ✅" : "Not enabled"}
                </p>
              </div>
              {(session.user as any).twoFactorEnabled ? (
                <button onClick={handleDisable2FA} style={styles.dangerBtn}>Disable 2FA</button>
              ) : (
                <button onClick={() => setShow2FASetup(true)} style={styles.enableBtn}>
                  Enable 2FA
                </button>
              )}
            </div>
          )}
        </div>

        {/* 2FA Setup Modal */}
        {show2FASetup && (
          <div style={styles.modal}>
            <div style={styles.modalCard}>
              <h3>Set up Two-Factor Authentication</h3>

              {setupStep === "password" && (
                <div style={styles.form}>
                  <p style={styles.hint}>Enter your password to begin 2FA setup</p>
                  <input
                    type="password"
                    placeholder="Your password"
                    value={setupPassword}
                    onChange={(e) => setSetupPassword(e.target.value)}
                    style={styles.input}
                  />
                  <button onClick={handleEnable2FA} style={styles.primaryBtn}>Continue</button>
                  <button onClick={() => setShow2FASetup(false)} style={styles.secondaryBtn}>Cancel</button>
                </div>
              )}

              {setupStep === "qr" && (
                <div style={styles.form}>
                  <p style={styles.hint}>
                    1. Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)
                  </p>
                  <div style={{ display: "flex", justifyContent: "center", padding: "16px" }}>
                    <QRCode value={totpURI} size={200} />
                  </div>
                  <p style={styles.hint}>2. Enter the 6-digit code from your app to confirm</p>
                  <input
                    type="text"
                    placeholder="000000"
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value)}
                    maxLength={6}
                    style={{ ...styles.input, textAlign: "center", letterSpacing: "4px" }}
                  />
                  {backupCodes.length > 0 && (
                    <div style={styles.backupCodesBox}>
                      <p style={{ fontWeight: 600, marginBottom: "8px" }}>
                        ⚠️ Save these backup codes in a secure place:
                      </p>
                      <div style={styles.codeGrid}>
                        {backupCodes.map((code: any, i: any) => (
                          <code key={i} style={styles.backupCode}>{code}</code>
                        ))}
                      </div>
                    </div>
                  )}
                  <button onClick={handleVerify2FA} style={styles.primaryBtn}>Verify & Enable</button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles: { [key: string]: React.CSSProperties } = {
  container: { minHeight: "100vh", background: "#f8fafc", fontFamily: "system-ui, sans-serif" },
  loading: { display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" },
  header: {
    background: "#fff", borderBottom: "1px solid #e2e8f0", padding: "0 24px",
    display: "flex", alignItems: "center", justifyContent: "space-between", height: "64px",
  },
  logo: { fontSize: "20px", fontWeight: 700, color: "#6366f1", margin: 0 },
  signOutBtn: {
    padding: "8px 16px", background: "#fff", border: "1px solid #e2e8f0",
    borderRadius: "6px", cursor: "pointer", fontSize: "14px",
  },
  content: { maxWidth: "680px", margin: "40px auto", padding: "0 24px" },
  welcomeCard: {
    background: "#fff", borderRadius: "12px", padding: "24px",
    display: "flex", alignItems: "center", gap: "20px",
    boxShadow: "0 1px 8px rgba(0,0,0,0.06)", marginBottom: "20px",
  },
  avatar: {
    width: "64px", height: "64px", borderRadius: "50%",
    background: "#6366f1", display: "flex", alignItems: "center", justifyContent: "center",
    overflow: "hidden", flexShrink: 0,
  },
  avatarImg: { width: "100%", height: "100%", objectFit: "cover" },
  avatarInitial: { color: "#fff", fontSize: "26px", fontWeight: 700 },
  userName: { margin: "0 0 4px", fontSize: "20px", fontWeight: 700, color: "#1e293b" },
  userEmail: { margin: "0 0 6px", color: "#64748b", fontSize: "14px" },
  badge: { margin: 0, fontSize: "13px", color: "#64748b" },
  securityCard: {
    background: "#fff", borderRadius: "12px", padding: "24px",
    boxShadow: "0 1px 8px rgba(0,0,0,0.06)",
  },
  sectionTitle: { margin: "0 0 16px", fontSize: "16px", fontWeight: 600, color: "#1e293b" },
  securityRow: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  securityLabel: { margin: "0 0 4px", fontWeight: 500, color: "#1e293b", fontSize: "14px" },
  securityValue: { margin: 0, color: "#64748b", fontSize: "13px" },
  enableBtn: {
    padding: "8px 16px", background: "#6366f1", color: "#fff", border: "none",
    borderRadius: "6px", cursor: "pointer", fontSize: "13px", fontWeight: 600,
  },
  dangerBtn: {
    padding: "8px 16px", background: "#fff", color: "#ef4444",
    border: "1px solid #ef4444", borderRadius: "6px", cursor: "pointer", fontSize: "13px",
  },
  modal: {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)",
    display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100,
  },
  modalCard: {
    background: "#fff", borderRadius: "12px", padding: "32px",
    maxWidth: "480px", width: "90%", maxHeight: "90vh", overflowY: "auto",
  },
  form: { display: "flex", flexDirection: "column", gap: "12px", marginTop: "16px" },
  input: {
    padding: "12px 14px", border: "1px solid #e2e8f0", borderRadius: "8px",
    fontSize: "15px", outline: "none", width: "100%", boxSizing: "border-box",
  },
  hint: { color: "#64748b", fontSize: "13px", margin: "0" },
  primaryBtn: {
    padding: "12px", background: "#6366f1", color: "#fff", border: "none",
    borderRadius: "8px", cursor: "pointer", fontSize: "15px", fontWeight: 600,
  },
  secondaryBtn: {
    padding: "10px", background: "#f1f5f9", color: "#1e293b",
    border: "1px solid #e2e8f0", borderRadius: "8px", cursor: "pointer", fontSize: "14px",
  },
  backupCodesBox: {
    background: "#fefce8", border: "1px solid #fde68a",
    borderRadius: "8px", padding: "16px", fontSize: "13px",
  },
  codeGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" },
  backupCode: {
    background: "#fff", border: "1px solid #e2e8f0", borderRadius: "4px",
    padding: "4px 8px", fontFamily: "monospace", fontSize: "13px",
  },
  oauthNotice: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: "8px",
    padding: "16px",
  },
  linkBtn: {
    background: "none",
    border: "none",
    color: "#6366f1",
    cursor: "pointer",
    fontSize: "14px",
    fontWeight: 600,
    padding: 0,
    textDecoration: "underline",
  },
};