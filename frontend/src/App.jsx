import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "./config/api";
import { clearPrivateCaches } from "./lib/clientCache";
import {
  currentEntryMatches,
  currentHistoryState,
  endSession,
  pathForForeignEntry,
  readAccountId,
  readEpoch,
  readStoredUserId,
  startSession,
  writeStoredUserId,
} from "./lib/historySession";
import { normalizePath, pathForPage, resolveRoute } from "./lib/routes";
import LoginPage from "./pages/LoginPage";
import { VerifyEmailPage, VerifyPending } from "./pages/VerifyEmail";
import { ResetPasswordPage } from "./pages/ResetPassword";
import { SettingsPage } from "./pages/Settings";
import { ConfirmEmailPage } from "./pages/ConfirmEmail";
import { ToastProvider } from "./components/Toast";
import { useToast } from "./components/toast-context";
import AppShell from "./components/layout/AppShell";
import useProfiles from "./hooks/useProfiles";
import { profileTitle } from "./lib/format";
import ProfilePage from "./pages/ProfilePage";
import DashboardPage from "./pages/DashboardPage";
import AdvisoryPage from "./pages/AdvisoryPage";
import ChatPage from "./pages/ChatPage";
import GoalsPage from "./pages/GoalsPage";

const FULL_BLEED = new Set(["profile", "chat"]);

function useAppPath() {
  const [path, setPath] = useState(() => normalizePath(window.location.pathname));

  const go = useCallback((page, { replace = false } = {}) => {
    const next = pathForPage(page);
    const current = normalizePath(window.location.pathname);
    const state = currentHistoryState();
    const sameUrl = next === current;
    if (sameUrl && currentEntryMatches() && !replace) {
      setPath(next);
      return;
    }
    if (replace || sameUrl) window.history.replaceState(state, "", next);
    else window.history.pushState(state, "", next);
    setPath(next);
  }, []);

  useEffect(() => {
    const onPop = () => {
      if (!currentEntryMatches()) {
        go(pathForForeignEntry(readEpoch(), readStoredUserId()), { replace: true });
        return;
      }
      setPath(normalizePath(window.location.pathname));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [go]);

  return [path, go];
}

function FinPilotApp({ account, onSignOut, path, go }) {
  const showToast = useToast();
  const profiles = useProfiles(showToast);
  const { users, remove } = profiles;

  const [activeUserId, setActiveUserId] = useState(readStoredUserId);

  // Persist selection; ignore stale ids once the profile list has loaded.
  const activeUser = useMemo(
    () => users.find((u) => u.id === activeUserId) || null,
    [users, activeUserId]
  );
  const staleSelection = !profiles.loading && activeUserId != null && !activeUser;
  const effectiveUserId = staleSelection ? null : activeUserId;
  const effectiveUser = staleSelection ? null : activeUser;

  useEffect(() => {
    writeStoredUserId(effectiveUserId);
  }, [effectiveUserId]);

  const activeGoal = effectiveUser ? profileTitle(effectiveUser) : "";

  const navigate = useCallback((page) => go(page), [go]);

  const selectUser = useCallback((id, list) => {
    setActiveUserId(id);
    writeStoredUserId(id);
    if (id) {
      const found = (list || users).find((u) => u.id === id);
      if (path === "/profile") go("/dashboard");
      return found;
    }
    return undefined;
  }, [users, path, go]);

  const handleCreated = useCallback(
    async (userId) => {
      await profiles.reload();
      setActiveUserId(userId);
      writeStoredUserId(userId);
      go("/dashboard");
    },
    [profiles, go]
  );

  const handleRemove = useCallback(
    async (id) => {
      await remove(id);
      if (id === activeUserId) {
        setActiveUserId(null);
        writeStoredUserId(null);
        go("/profile", { replace: true });
      }
    },
    [remove, activeUserId, go]
  );

  const newProfile = useCallback(() => go("/profile"), [go]);

  const profilesForPage = { ...profiles, remove: handleRemove };
  const hasUser = !!effectiveUserId;
  const decision = resolveRoute({ signedIn: true, path, profileId: effectiveUserId });
  const page = decision.screen;

  useEffect(() => {
    if (decision.redirect) go(decision.redirect, { replace: true });
  }, [decision.redirect, go]);

  return (
    <AppShell
      activePage={page}
      path={decision.redirect || path}
      onNavigate={navigate}
      hasUser={hasUser}
      activeGoal={activeGoal}
      onNewProfile={newProfile}
      onSettings={() => go("/settings")}
      fullBleed={FULL_BLEED.has(page)}
      accountEmail={account.email}
      onSignOut={onSignOut}
    >
      {page === "profile" && (
        <ProfilePage
          onCreated={handleCreated}
          activeUserId={effectiveUserId}
          onSelectUser={selectUser}
          profiles={profilesForPage}
        />
      )}
      {page === "dashboard" && hasUser && (
        <DashboardPage userId={effectiveUserId} user={effectiveUser} userGoal={activeGoal} onNavigate={navigate} />
      )}
      {page === "advisory" && hasUser && (
        <AdvisoryPage key={effectiveUserId} userId={effectiveUserId} userGoal={activeGoal} />
      )}
      {page === "chat" && hasUser && (
        <ChatPage key={effectiveUserId} userId={effectiveUserId} userGoal={activeGoal} />
      )}
      {page === "goals" && hasUser && (
        <GoalsPage key={effectiveUserId} userId={effectiveUserId} userGoal={activeGoal} />
      )}
      {page === "settings" && (
        <SettingsPage account={account} onLeft={onSignOut} />
      )}
    </AppShell>
  );
}

export default function App() {
  const [account, setAccount] = useState(null);
  const [ready, setReady] = useState(false);
  const [path, go] = useAppPath();
  const accountRef = useRef(null);
  accountRef.current = account;

  const signIn = useCallback((me) => {
    startSession(me.account_id);
    clearPrivateCaches();
    go(normalizePath(window.location.pathname), { replace: true });
    setAccount(me);
  }, [go]);

  const dropSession = useCallback(() => {
    endSession();
    clearPrivateCaches();
    go("/", { replace: true });
    setAccount(null);
  }, [go]);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/auth/me")
      .then((me) => {
        if (cancelled || accountRef.current) return;
        if (readAccountId() !== String(me.account_id)) {
          startSession(me.account_id);
          clearPrivateCaches();
        }
        go(normalizePath(window.location.pathname), { replace: true });
        setAccount(me);
      })
      .catch(() => {
        if (cancelled || accountRef.current) return;
        endSession();
        clearPrivateCaches();
        setAccount(null);
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    const expired = () => dropSession();
    const onPageShow = (event) => {
      if (!event.persisted) return;
      apiFetch("/auth/me")
        .then((me) => {
          if (readAccountId() === String(me.account_id)) return;
          startSession(me.account_id);
          clearPrivateCaches();
          go(pathForForeignEntry(readEpoch(), null), { replace: true });
          setAccount(me);
        })
        .catch(() => dropSession());
    };
    window.addEventListener("finpilot:session-expired", expired);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      cancelled = true;
      window.removeEventListener("finpilot:session-expired", expired);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [dropSession, go]);

  const signOut = useCallback(async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      /* cookie clear is enough */
    }
    dropSession();
  }, [dropSession]);

  const onVerifyLink = path === "/verify-email";
  const onResetLink = path === "/reset-password";
  const onConfirmEmail = path === "/confirm-email";
  const signedOut = resolveRoute({ signedIn: false, path, profileId: null });

  useEffect(() => {
    if (!ready || account) return;
    if (signedOut.redirect) go(signedOut.redirect, { replace: true });
  }, [ready, account, signedOut.redirect, go]);

  return (
    <ToastProvider>
      {!ready ? null : (
        <div key={account ? account.account_id : "landing"} className="view-enter">
          {onConfirmEmail ? (
            <ConfirmEmailPage onDone={() => {
              endSession();
              clearPrivateCaches();
              setAccount(null);
              go("/", { replace: true });
            }} />
          ) : onResetLink ? (
            <ResetPasswordPage onDone={() => {
              endSession();
              clearPrivateCaches();
              setAccount(null);
              go("/", { replace: true });
            }} />
          ) : onVerifyLink ? (
            <VerifyEmailPage onConfirmed={async () => {
              const me = await apiFetch("/auth/me");
              setAccount(me);
              go("/profile", { replace: true });
            }} />
          ) : account && account.email_verified === false ? (
            <VerifyPending account={account} onSignOut={signOut} />
          ) : account ? (
            <FinPilotApp account={account} onSignOut={signOut} path={path} go={go} />
          ) : (
            <LoginPage onSignedIn={signIn} />
          )}
        </div>
      )}
    </ToastProvider>
  );
}
