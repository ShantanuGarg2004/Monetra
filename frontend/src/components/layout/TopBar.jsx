import Icon from "../Icon";

export default function TopBar({ title, activeGoal, onNewProfile, onMenu, onSettings }) {
  return (
    <header className="fixed top-0 right-0 left-0 lg:left-56 z-30 min-h-[var(--app-bar)] pt-[env(safe-area-inset-top)] bg-background/85 backdrop-blur-md border-b border-outline flex justify-between items-center px-3 sm:px-gutter gap-2">
      <div className="flex items-center gap-1 min-w-0">
        <button onClick={onMenu} aria-label="Open menu" className="lg:hidden min-h-11 min-w-11 -ml-1 inline-flex items-center justify-center text-on-surface-variant hover:text-primary shrink-0">
          <Icon name="menu" size={22} />
        </button>
        <h2 className="font-headline-md text-[16px] leading-6 sm:text-headline-md font-semibold text-on-surface truncate">{title}</h2>
      </div>

      <div className="flex items-center gap-sm shrink-0">
        {activeGoal && (
          <div className="hidden xl:block max-w-[220px] truncate text-[12px] text-on-surface-variant bg-surface border border-outline rounded-full px-3 py-1.5">
            {activeGoal}
          </div>
        )}

        <div className="relative w-48 hidden lg:block">
          <Icon name="search" size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" />
          <input
            className="w-full bg-surface border border-outline rounded-full py-1.5 pl-9 pr-3 text-[12px] text-on-surface focus:outline-none focus:border-primary transition-colors placeholder:text-on-surface-variant/50"
            placeholder="Search…"
            type="text"
          />
        </div>

        <div className="flex items-center gap-0.5">
          <button onClick={onNewProfile} title="New profile" className="p-1.5 text-on-surface-variant hover:text-primary transition-colors">
            <Icon name="person_add" size={18} />
          </button>
          <button className="hidden sm:inline-flex p-1.5 text-on-surface-variant hover:text-primary transition-colors">
            <Icon name="notifications" size={18} />
          </button>
          <button type="button" onClick={onSettings} aria-label="Settings" className="inline-flex p-1.5 text-on-surface-variant hover:text-primary transition-colors">
            <Icon name="settings" size={18} />
          </button>
          <div className="h-8 w-8 ml-1 rounded-full border border-outline bg-surface-container flex items-center justify-center text-primary shrink-0">
            <Icon name="account_circle" size={22} />
          </div>
        </div>
      </div>
    </header>
  );
}
