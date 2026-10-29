import { useToast } from "../components/toast-context";
import useReport from "../hooks/useReport";
import { scoreStatus } from "../lib/format";
import Icon from "../components/Icon";
import Button from "../components/Button";
import Spinner from "../components/Spinner";
import GlassPanel from "../components/GlassPanel";
import GaugeRing from "../components/GaugeRing";
import ProgressBar from "../components/ProgressBar";
import EmptyState from "../components/EmptyState";
import LoadErrorBanner from "../components/LoadErrorBanner";
import MarkdownRenderer from "../lib/markdown";
import PillarPerformance from "../sections/shared/PillarPerformance";

const SectionLabel = ({ children, right }) => (
  <div className="flex items-center justify-between mb-sm">
    <h3 className="font-label-sm text-label-sm text-primary uppercase tracking-wider">{children}</h3>
    {right}
  </div>
);

export default function AdvisoryPage({ userId, userGoal }) {
  const showToast = useToast();
  const { report, fetching, generating, generate, download, loadError, retryLoad } = useReport(userId, showToast);

  const health = report?.health || {};
  const status = scoreStatus(health.score || 0);

  const savings = Number(health.savings_ratio ?? 0);
  const expenses = Number(health.expense_ratio ?? 0);
  const investable = Math.max(0, 100 - savings - expenses);

  const missingReport = !report && (loadError?.code === "not_found" || loadError?.status === 404 || (!loadError && !fetching));
  const blockedLoad = !report && loadError && loadError.code !== "not_found" && loadError.status !== 404;

  return (
    <div className="max-w-[840px] mx-auto">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-end mb-lg sm:mb-2xl border-b border-outline pb-md">
        <div className="min-w-0">
          <h2 className="font-headline-lg text-[22px] leading-7 sm:text-headline-lg text-on-surface">AI Advisory Report</h2>
          <p className="text-[12px] text-on-surface-variant mt-0.5 truncate">
            {userGoal || `Profile #${userId}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {report && (
            <Button variant="subtle" size="sm" icon="download" onClick={download}>
              PDF
            </Button>
          )}
          <Button
            variant="container"
            size="sm"
            icon={report ? "refresh" : "auto_awesome"}
            loading={generating}
            loadingText="Generating…"
            onClick={generate}
          >
            {report ? "Regenerate" : "Generate"}
          </Button>
        </div>
      </div>

      <LoadErrorBanner error={loadError} onRetry={retryLoad} resource="report" />

      {fetching ? (
        <div className="flex items-center gap-2 text-on-surface-variant text-sm">
          <Spinner size={16} /> Loading report…
        </div>
      ) : missingReport ? (
        <EmptyState
          icon="analytics"
          title="No report yet"
          description="Generate a comprehensive AI advisory report based on this profile's financial health."
          action={{ label: "Generate Report", icon: "auto_awesome", onClick: generate }}
        />
      ) : blockedLoad ? (
        <EmptyState
          icon="cloud_off"
          title="Report unavailable right now"
          description="The server still may have your saved report. Use Retry above, or wait out rate limits before regenerating."
          action={{ label: "Retry load", icon: "refresh", onClick: retryLoad }}
        />
      ) : report ? (
        <div className="space-y-md">
          <section>
            <SectionLabel>01. Executive Summary</SectionLabel>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-sm">
              <GlassPanel className="md:col-span-2 p-md">
                <h4 className="font-headline-md text-headline-md text-on-surface mb-1">Portfolio Health</h4>
                <p className="text-[12px] text-on-surface-variant mb-sm">
                  Rated <span style={{ color: status.color }}>{status.label}</span> — blends savings, expense control, emergency buffer and long-term readiness.
                </p>
                <div className="flex items-center gap-md">
                  <div>
                    <span className="font-label-sm text-label-sm text-on-surface-variant block">Savings Rate</span>
                    <span className="font-currency-xl text-currency-xl text-primary">{savings}%</span>
                  </div>
                  <div className="h-8 w-px bg-white/10" />
                  <div>
                    <span className="font-label-sm text-label-sm text-on-surface-variant block">Emergency Fund</span>
                    <span className="font-headline-md text-headline-md text-tertiary">{health.emg_months ?? 0} mo</span>
                  </div>
                </div>
              </GlassPanel>

              <GlassPanel className="p-md flex flex-col justify-center items-center text-center">
                <span className="font-label-sm text-label-sm text-on-surface-variant uppercase mb-1">Health Score</span>
                <GaugeRing value={health.score || 0} size={100} stroke={7} color={status.color} />
                <span className="font-label-sm text-label-sm mt-1.5" style={{ color: status.color }}>
                  {status.label.toUpperCase()}
                </span>
              </GlassPanel>
            </div>
          </section>

          <section>
            <SectionLabel>02. Budget Optimization</SectionLabel>
            <GlassPanel className="p-md">
              <div className="flex justify-between items-start mb-md gap-3">
                <div>
                  <h4 className="font-headline-md text-headline-md text-on-surface">Monthly Cash Flow</h4>
                  <p className="text-[12px] text-on-surface-variant">
                    Essentials, savings and investable surplus as % of income.
                  </p>
                </div>
                <div className="bg-tertiary-container/20 border border-tertiary/30 px-sm py-1.5 rounded-md text-center shrink-0">
                  <span className="font-label-sm text-label-sm text-tertiary block">Investable</span>
                  <span className="font-headline-md text-headline-md text-tertiary">{investable}%</span>
                </div>
              </div>
              <div className="space-y-md">
                {[
                  { label: "Essential Expenses", pct: expenses, color: "#9AA8BC" },
                  { label: "Savings Rate", pct: savings, color: "#18B981" },
                  { label: "Investment Capacity (Surplus)", pct: investable, color: "#6B9BCF" },
                ].map((r) => (
                  <div key={r.label}>
                    <div className="flex justify-between font-label-sm text-label-sm text-on-surface-variant mb-2">
                      <span>{r.label}</span>
                      <span>{r.pct}% of Income</span>
                    </div>
                    <ProgressBar pct={r.pct} color={r.color} height={8} />
                  </div>
                ))}
              </div>
            </GlassPanel>
          </section>

          {/* 03 Pillar Breakdown */}
          <section>
            <SectionLabel>03. Pillar Breakdown</SectionLabel>
            <GlassPanel className="p-md">
              <PillarPerformance pillarScores={health.pillar_scores} variant="list" />
            </GlassPanel>
          </section>

          {/* 04 Strengths & Improvements */}
          {(health.insights?.length > 0 || health.warnings?.length > 0) && (
            <section>
              <SectionLabel>04. Strengths &amp; Improvements</SectionLabel>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-md">
                {health.insights?.length > 0 && (
                  <div className="bg-tertiary/5 border border-tertiary/15 rounded-xl p-md">
                    <div className="font-label-sm text-label-sm uppercase text-tertiary mb-3 flex items-center gap-1.5">
                      <Icon name="check_circle" size={16} fill /> Strengths
                    </div>
                    <ul className="space-y-2">
                      {health.insights.map((item, i) => (
                        <li key={i} className="flex gap-2 text-sm text-tertiary-fixed leading-relaxed">
                          <Icon name="check" size={16} className="text-tertiary shrink-0 mt-0.5" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {health.warnings?.length > 0 && (
                  <div className="bg-primary/5 border border-primary/15 rounded-xl p-md">
                    <div className="font-label-sm text-label-sm uppercase text-primary mb-3 flex items-center gap-1.5">
                      <Icon name="priority_high" size={16} fill /> Areas to Improve
                    </div>
                    <ul className="space-y-2">
                      {health.warnings.map((w, i) => (
                        <li key={i} className="flex gap-2 text-sm text-primary-fixed leading-relaxed">
                          <Icon name="chevron_right" size={16} className="text-primary shrink-0 mt-0.5" />
                          <span>{w}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* 05 AI Advisory */}
          {report.ai_report && (
            <section>
              <SectionLabel>05. AI Advisory</SectionLabel>
              <GlassPanel className="p-md">
                <div className="font-label-sm text-label-sm uppercase text-primary mb-sm flex items-center gap-1.5">
                  <Icon name="auto_awesome" size={14} fill /> Strategic Recommendations
                </div>
                <MarkdownRenderer content={report.ai_report} />
              </GlassPanel>
            </section>
          )}

          <footer className="mt-md pt-md border-t border-outline text-center">
            <p className="text-[10px] text-on-surface-variant/40 leading-relaxed max-w-lg mx-auto">
              Generated by Monetra. Investments are subject to market risks. Not a SEBI-registered advisor.
            </p>
          </footer>
        </div>
      ) : null}
    </div>
  );
}
