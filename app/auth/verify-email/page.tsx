// app/auth/verify-email/page.tsx
"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authClient } from "@/lib/auth-client";

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    // Better Auth handles the actual verification via the callbackURL
    // By the time the user lands here they're already verified
    // We just check session and redirect
    authClient.getSession().then(({ data }) => {
      if (data?.session) {
        setStatus("success");
        setTimeout(() => router.push("/dashboard"), 2000);
      } else {
        setStatus("error");
        setMessage("Verification link may have expired. Please request a new one.");
      }
    });
  }, [router]);

  return (
    <div style={center}>
      <div style={card}>
        {status === "loading" && (
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "32px", marginBottom: "16px" }}>⏳</div>
            <h2>Verifying your email...</h2>
          </div>
        )}
        {status === "success" && (
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "32px", marginBottom: "16px" }}>✅</div>
            <h2 style={{ color: "#22c55e" }}>Email verified!</h2>
            <p style={{ color: "#64748b" }}>Redirecting you to the dashboard...</p>
          </div>
        )}
        {status === "error" && (
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "32px", marginBottom: "16px" }}>❌</div>
            <h2 style={{ color: "#ef4444" }}>Verification failed</h2>
            <p style={{ color: "#64748b" }}>{message}</p>
            <a href="/auth" style={{ color: "#6366f1" }}>Back to sign in</a>
          </div>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div style={center}>Loading...</div>}>
      <VerifyEmailContent />
    </Suspense>
  );
}

const center: React.CSSProperties = {
  minHeight: "100vh", display: "flex",
  alignItems: "center", justifyContent: "center", background: "#f8fafc",
};
const card: React.CSSProperties = {
  background: "#fff", borderRadius: "12px", padding: "40px",
  maxWidth: "400px", width: "100%", boxShadow: "0 4px 24px rgba(0,0,0,0.08)",
  textAlign: "center",
};