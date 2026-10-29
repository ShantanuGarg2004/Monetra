import { useState } from "react";
import Button from "../components/Button";
import { TextField } from "../components/Field";
import { apiFetch } from "../config/api";

function Notice({ children }) {
  if (!children) return null;
  return <p className="text-sm leading-6 text-primary">{children}</p>;
}

export function SettingsPage({ account, onLeft }) {
  const [leftMessage, setLeftMessage] = useState("");

  if (leftMessage) {
    return (
      <section className="max-w-lg rounded-xl border border-outline bg-surface p-5">
        <p className="text-sm leading-6 text-on-surface">{leftMessage}</p>
        <Button type="button" className="mt-4" onClick={onLeft}>Sign in</Button>
      </section>
    );
  }

  return (
    <div className="max-w-lg space-y-lg">
      <ChangePassword onLeft={setLeftMessage} />
      <ChangeEmail />
      <DeleteAccount email={account.email} onLeft={setLeftMessage} />
    </div>
  );
}

function ChangePassword({ onLeft }) {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState("");
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
      const body = await apiFetch("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: current,
          password,
          confirm_password: confirm,
        }),
      });
      onLeft(body.message || "You will need to sign in again on each device.");
    } catch (err) {
      setMessage(err.message || "Password could not be changed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-xl border border-outline bg-surface p-5">
      <h2 className="font-headline-md text-headline-md text-on-surface">Change password</h2>
      <p className="mt-2 text-[13px] leading-5 text-on-surface-variant">You will need to sign in again on each device.</p>
      <form onSubmit={submit} className="mt-4 space-y-4">
        <TextField label="Current password" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoComplete="current-password" />
        <TextField label="New password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="new-password" />
        <p className="text-[12px] leading-5 text-on-surface-variant">Password must be at least 12 characters.</p>
        <TextField label="Confirm password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required autoComplete="new-password" />
        <Notice>{message}</Notice>
        <Button type="submit" loading={loading}>Change password</Button>
      </form>
    </section>
  );
}

function ChangeEmail() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    setLoading(true);
    try {
      const body = await apiFetch("/auth/change-email", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setMessage(body.message || "Confirm the new address from the link we sent.");
      setEmail("");
      setPassword("");
    } catch (err) {
      setMessage(err.message || "Email could not be changed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-xl border border-outline bg-surface p-5">
      <h2 className="font-headline-md text-headline-md text-on-surface">Change email</h2>
      <p className="mt-2 text-[13px] leading-5 text-on-surface-variant">This address stays until the new one confirms the link.</p>
      <form onSubmit={submit} className="mt-4 space-y-4">
        <TextField label="New email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        <TextField label="Current password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        <Notice>{message}</Notice>
        <Button type="submit" loading={loading}>Send confirmation</Button>
      </form>
    </section>
  );
}

function DeleteAccount({ email, onLeft }) {
  const [password, setPassword] = useState("");
  const [typed, setTyped] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    setLoading(true);
    try {
      const body = await apiFetch("/auth/delete-account", {
        method: "POST",
        body: JSON.stringify({ password, email: typed }),
      });
      onLeft(body.message || "Account deleted.");
    } catch (err) {
      setMessage(err.message || "Account could not be deleted.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-xl border border-outline bg-surface p-5">
      <h2 className="font-headline-md text-headline-md text-on-surface">Delete account</h2>
      <p className="mt-2 text-[13px] leading-5 text-on-surface-variant">
        Type {email} and the current password. This removes the account and its profiles.
      </p>
      <form onSubmit={submit} className="mt-4 space-y-4">
        <TextField label="Current password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        <TextField label="Account email" type="email" value={typed} onChange={(e) => setTyped(e.target.value)} required autoComplete="off" />
        <Notice>{message}</Notice>
        <Button type="submit" variant="danger" loading={loading}>Delete account</Button>
      </form>
    </section>
  );
}
