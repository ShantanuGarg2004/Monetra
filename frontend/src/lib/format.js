/* Status + progress colors mapped to the Monetra navy/emerald system. */

export function profileTitle(user) {
  if (!user) return "";
  const goals = (user.financial_goals || "").trim();
  if (!goals) return `Profile #${user.id}`;
  return goals.length > 52 ? goals.slice(0, 49) + "…" : goals;
}

export function formatINR(value) {
  const n = Number(value) || 0;
  return n.toLocaleString("en-IN");
}

export function compactINR(value) {
  const n = Number(value) || 0;
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  return `₹${formatINR(Math.round(n))}`;
}

export const RISK_OPTIONS = [
  { value: "low", label: "Conservative", hint: "Preserve Capital", icon: "shield" },
  { value: "medium", label: "Balanced", hint: "Growth & Stability", icon: "balance" },
  { value: "high", label: "Aggressive", hint: "Maximum Returns", icon: "trending_up" },
];

export function scoreStatus(score) {
  if (score >= 70) return { label: "Healthy", color: "#18B981" };
  if (score >= 50) return { label: "Moderate", color: "#F4B740" };
  return { label: "At Risk", color: "#F06A6A" };
}

export function pctColor(pct) {
  if (pct >= 70) return "#18B981";
  if (pct >= 40) return "#F4B740";
  return "#F06A6A";
}

export const PILLAR_META = [
  { key: "savings_rate", label: "Savings Rate", max: 25 },
  { key: "expense_control", label: "Expense Control", max: 20 },
  { key: "emergency_fund", label: "Emergency Fund", max: 20 },
  { key: "debt_ratio", label: "Debt-to-Income", max: 15 },
  { key: "retirement", label: "Retirement", max: 10 },
  { key: "tax_efficiency", label: "Tax Efficiency", max: 5 },
  { key: "surplus_buffer", label: "Surplus Buffer", max: 5 },
];
