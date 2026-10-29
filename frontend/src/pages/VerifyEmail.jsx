import { useState } from "react";
import Button from "../components/Button";
import { apiFetch } from "../config/api";

export function VerifyPending({ account, onSignOut }) {
  const [message, setMessage] = useState(account.message || "");
  const [loading, setLoading] = useState(false);

  async function resend() {
    setLoading(true);
    try {
      const body = await apiFetch("/auth/resend-verification", { method: "POST" });
      setMessage(body.message || "Verification email sent.");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="landing-page">
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
        <h1 className="font-display text-3xl font-bold text-white">Confirm your email.</h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          We sent a confirmation link to {account.email}. This happens once, when the account is created. After you confirm it, signing in uses a code sent to that same address.
        </p>
        {message && <p className="mt-4 text-sm leading-6 text-gold">{message}</p>}
        <Button type="button" loading={loading} className="mt-6" onClick={resend}>Resend email</Button>
        <button type="button" className="mt-4 text-[13px] font-semibold text-gold" onClick={onSignOut}>Sign out</button>
      </main>
    </div>
  );
}

export function VerifyEmailPage({ proof, onConfirmed, onSignIn }) {
  const [message, setMessage] = useState("");
  const [done, setDone] = useState(false);
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const [loading, setLoading] = useState(false);

  async function confirm() {
    setLoading(true);
    setMessage("");
    try {
      await apiFetch("/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ id: proof.id, token: proof.token }),
      });
      setDone(true);
      try {
        await onConfirmed();
      } catch {
        setNeedsSignIn(true);
        setMessage("Email confirmed. Sign in to continue.");
      }
    } catch (err) {
      setMessage(err.message || "That link is invalid or expired.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="landing-page">
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
        <h1 className="font-display text-3xl font-bold text-white">Confirm your email.</h1>
        <p className="mt-3 text-sm leading-6 text-muted">Press the button to finish. Opening this page does not use the link.</p>
        {message && <p className="mt-4 text-sm leading-6 text-gold">{message}</p>}
        {needsSignIn ? (
          <Button type="button" className="mt-6" onClick={onSignIn}>Sign in</Button>
        ) : !done && (
          <Button type="button" loading={loading} className="mt-6" onClick={confirm}>Confirm email</Button>
        )}
      </main>
    </div>
  );
}
