/* Primary navigation model shared by the sidebar.
   `requiresUser` items are disabled until a profile is selected. */
export const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: "dashboard", requiresUser: true },
  { id: "advisory", label: "Advisory", icon: "description", requiresUser: true },
  { id: "chat", label: "Chat", icon: "chat_bubble", requiresUser: true },
  { id: "goals", label: "Goals", icon: "insights", requiresUser: true },
  { id: "profile", label: "Profile", icon: "person", requiresUser: false },
];

export const PAGE_TITLES = {
  dashboard: "Dashboard Overview",
  advisory: "AI Advisory Report",
  chat: "AI Advisor Chat",
  goals: "Goal Simulator",
  profile: "Onboarding Profile",
  settings: "Settings",
};
