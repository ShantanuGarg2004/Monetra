import { useState } from "react";
import Button from "../components/Button";
import { TextField } from "../components/Field";
import { apiFetch } from "../config/api";

export function ResetPasswordPage({ onDone, proof }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    if (password !== confirm) {
      setMessage("Confirm password must match password.");
      return;
    }
    setLoading(true);
    try {
      const body = await apiFetch("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({
          id: proof.id,
          token: proof.token,
          password,
          confirm_password: confirm,
        }),
      });
      setDone(true);
      setMessage(body.message || "You will need to sign in again on each device.");
    } catch (err) {
      setMessage(err.message || "That link is invalid or expired.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="landing-page">
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
        <h1 className="font-display text-3xl font-bold text-white">Choose a new password.</h1>
        <p className="mt-3 text-sm leading-6 text-muted">You will need to sign in again on each device. Opening this page does not use the link.</p>
        {done ? (
          <>
            {message && <p className="mt-4 text-sm leading-6 text-gold">{message}</p>}
            <Button type="button" className="mt-6" onClick={onDone}>Sign in</Button>
          </>
        ) : (
          <form onSubmit={submit} className="mt-6 space-y-4">
            <TextField label="New password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="new-password" />
            <p className="text-[12px] leading-5 text-muted">Password must be at least 12 characters.</p>
            <TextField label="Confirm password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required autoComplete="new-password" />
            {message && <p className="text-sm leading-6 text-gold">{message}</p>}
            <Button type="submit" loading={loading} className="w-full">Set new password</Button>
          </form>
        )}
      </main>
    </div>
  );
}
