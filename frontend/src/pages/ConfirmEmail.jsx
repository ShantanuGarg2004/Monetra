import { useState } from "react";
import Button from "../components/Button";
import { apiFetch } from "../config/api";

export function ConfirmEmailPage({ onDone, proof }) {
  const [message, setMessage] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  async function confirm() {
    setLoading(true);
    setMessage("");
    try {
      const body = await apiFetch("/auth/confirm-email", {
        method: "POST",
        body: JSON.stringify({ id: proof.id, token: proof.token }),
      });
      setDone(true);
      setMessage(body.message || "Email updated. Sign in again with the new address.");
    } catch (err) {
      setMessage(err.message || "That link is invalid or expired.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="landing-page">
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
        <h1 className="font-display text-3xl font-bold text-white">Confirm this email.</h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          Press the button to move the account to this address. You will need to sign in again with the new address. Opening this page does not use the link.
        </p>
        {message && <p className="mt-4 text-sm leading-6 text-gold">{message}</p>}
        {done ? (
          <Button type="button" className="mt-6" onClick={onDone}>Sign in</Button>
        ) : (
          <Button type="button" loading={loading} className="mt-6" onClick={confirm}>Confirm email</Button>
        )}
      </main>
    </div>
  );
}
