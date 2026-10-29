import { useEffect } from "react";
import Icon from "../Icon";
import { NAV_ITEMS } from "./nav";

export default function Sidebar({ activePage, onNavigate, hasUser, open, onClose, accountEmail, onSignOut }) {
  useEffect(() => {
    if (!open) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  return (
    <>
      <div
        onClick={onClose}
        className={`fixed inset-0 bg-black/50 z-40 lg:hidden transition-opacity duration-200 ${
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
      />

      <aside
        className={`fixed h-screen w-56 left-0 top-0 border-r border-outline bg-surface flex flex-col py-lg z-50 transform transition-transform duration-200 lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="px-md mb-lg flex items-center justify-between">
          <div className="min-w-0">
            <h1 className="font-headline-md text-[18px] font-bold text-on-surface leading-tight truncate">
              Monetra
            </h1>
            <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mt-1">
              Wealth Manager
            </p>
          </div>
          <button onClick={onClose} aria-label="Close menu" className="lg:hidden min-h-11 min-w-11 inline-flex items-center justify-center text-on-surface-variant hover:text-primary">
            <Icon name="close" size={18} />
          </button>
        </div>

        <nav className="flex-1 px-sm space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const disabled = item.requiresUser && !hasUser;
            const active = activePage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => !disabled && onNavigate(item.id)}
                disabled={disabled}
                title={disabled ? "Select or create a profile first" : undefined}
                className={[
                  "w-full flex items-center gap-sm pl-3 py-3 rounded-lg transition-colors duration-150 text-left font-medium",
                  active
                    ? "text-primary bg-surface-container border-l-2 border-primary"
                    : disabled
                    ? "text-on-surface-variant/40 cursor-default"
                    : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
                ].join(" ")}
              >
                <Icon name={item.icon} size={18} fill={active} />
                <span className="text-[13px]">{item.label}</span>
                {disabled && <Icon name="lock" size={14} className="ml-auto mr-2 opacity-40" />}
              </button>
            );
          })}
        </nav>

        <div className="px-md mt-auto pt-md space-y-2">
          {accountEmail && (
            <p className="text-[12px] text-on-surface-variant truncate" title={accountEmail}>{accountEmail}</p>
          )}
          <button type="button" onClick={onSignOut} className="w-full min-h-11 py-2 text-[13px] text-on-surface-variant hover:text-on-surface text-left">
            Sign out
          </button>
          <button className="w-full py-2.5 bg-premium text-background text-[13px] font-semibold rounded-lg hover:opacity-90 transition-all flex items-center justify-center gap-1.5">
            <Icon name="star" size={16} fill />
            Upgrade to Elite
          </button>
        </div>
      </aside>
    </>
  );
}
