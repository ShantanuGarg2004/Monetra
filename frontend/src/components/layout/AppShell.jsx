import { useCallback, useState } from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { PAGE_TITLES } from "./nav";

export default function AppShell({ activePage, path, onNavigate, hasUser, activeGoal, onNewProfile, onSettings, fullBleed = false, accountEmail, onSignOut, children }) {
  const [open, setOpen] = useState(false);

  const navigate = useCallback(
    (page) => {
      onNavigate(page);
      setOpen(false);
    },
    [onNavigate]
  );

  return (
    <div className="min-h-screen bg-background text-on-surface">
      <Sidebar activePage={activePage} onNavigate={navigate} hasUser={hasUser} open={open} onClose={() => setOpen(false)} accountEmail={accountEmail} onSignOut={onSignOut} />
      <TopBar
        title={PAGE_TITLES[activePage]}
        activeGoal={activeGoal}
        onNewProfile={onNewProfile}
        onSettings={onSettings}
        onMenu={() => setOpen(true)}
      />

      {fullBleed ? (
        <main className="lg:ml-56 pt-[var(--app-bar)] min-h-dvh lg:h-dvh lg:overflow-hidden overflow-x-hidden">
          <div key={path || activePage} className="page-enter min-h-0">{children}</div>
        </main>
      ) : (
        <main className="lg:ml-56 pt-[var(--app-bar)] min-h-dvh px-4 pb-xl sm:px-gutter md:px-lg">
          <div key={path || activePage} className="page-enter max-w-container-max mx-auto space-y-lg pt-lg md:pt-2xl">{children}</div>
        </main>
      )}
    </div>
  );
}
