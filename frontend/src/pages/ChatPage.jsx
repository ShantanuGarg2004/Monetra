import { useState } from "react";
import { useToast } from "../components/toast-context";
import useChat from "../hooks/useChat";
import Icon from "../components/Icon";
import Spinner from "../components/Spinner";
import MarkdownRenderer from "../lib/markdown";
import LoadErrorBanner from "../components/LoadErrorBanner";

const PROMPTS = [
  { icon: "account_balance_wallet", color: "text-primary", label: "Portfolio Analysis", query: "Analyze my current financial situation and suggest how to improve my portfolio." },
  { icon: "query_stats", color: "text-tertiary", label: "Tax Optimization", query: "How can I optimize my taxes given my income and savings?" },
  { icon: "auto_awesome", color: "text-primary", label: "Goal Simulation", query: "Help me plan and evaluate the feasibility of my financial goals." },
];

export default function ChatPage({ userId, userGoal }) {
  const showToast = useToast();
  const { messages, fetching, sending, send, clear, bottomRef, loadError, retryLoad } = useChat(userId, showToast);
  const [input, setInput] = useState("");

  const submit = () => {
    if (!input.trim() || sending) return;
    send(input);
    setInput("");
  };

  return (
    <div className="h-[calc(100dvh-var(--app-bar))] flex min-w-0">
      <section className="w-64 xl:w-72 border-r border-outline hidden md:flex flex-col bg-surface/60 shrink-0">
        <div className="p-md space-y-sm">
          <h3 className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant opacity-70">
            Strategic Prompts
          </h3>
          <div className="space-y-1">
            {PROMPTS.map((p) => (
              <button
                key={p.label}
                onClick={() => !sending && send(p.query)}
                className="w-full flex items-center justify-between px-sm py-2 rounded-md border border-outline/60 bg-surface-container hover:bg-surface-container-high transition-all text-left group"
              >
                <div className="flex items-center gap-sm min-w-0">
                  <Icon name={p.icon} size={16} className={p.color} />
                  <span className="text-[12px] text-on-surface truncate">{p.label}</span>
                </div>
                <Icon name="arrow_forward" size={14} className="text-on-surface-variant opacity-0 group-hover:opacity-100" />
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-md pb-md">
          <div className="flex items-center justify-between mb-sm">
            <h3 className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant opacity-70">
              Conversation
            </h3>
            {messages.length > 0 && (
              <button onClick={clear} className="text-[11px] text-on-surface-variant hover:text-error flex items-center gap-0.5">
                <Icon name="delete" size={13} /> Clear
              </button>
            )}
          </div>
          <div className="px-sm py-2 rounded-md bg-surface-container-high border-l-2 border-primary">
            <p className="text-[12px] font-semibold truncate text-primary">{userGoal || `Profile #${userId}`}</p>
            <span className="text-[11px] text-on-surface-variant">Active now</span>
          </div>
        </div>
      </section>

      <section className="flex-1 flex flex-col relative bg-surface-container-lowest min-w-0 min-h-0">
        <div className="px-md pt-md">
          <LoadErrorBanner error={loadError} onRetry={retryLoad} resource="chat history" />
        </div>
        <div className="flex-1 overflow-y-auto p-md space-y-md">
          {fetching ? (
            <div className="flex items-center gap-2 text-on-surface-variant text-[12px]">
              <Spinner size={14} /> Loading conversation…
            </div>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-on-surface-variant">
              <div className="w-11 h-11 rounded-xl bg-info/15 border border-info/30 flex items-center justify-center mb-sm">
                <Icon name="smart_toy" className="text-info" size={22} />
              </div>
              <p className="text-[13px] max-w-xs">
                Ask about investments, budgeting, tax savings, or your goals.
              </p>
            </div>
          ) : (
            messages.map((m, i) =>
              m.role === "ai" ? (
                <div key={i} className="flex items-start gap-sm max-w-[min(42rem,100%)] min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-info/15 border border-info/30 flex items-center justify-center shrink-0">
                    <Icon name="smart_toy" size={16} className="text-info" />
                  </div>
                  <div className="bg-surface-container border border-outline/60 px-md py-sm rounded-xl rounded-tl-sm min-w-0 break-words">
                    <MarkdownRenderer content={m.message} />
                  </div>
                </div>
              ) : (
                <div key={i} className="flex items-start gap-sm max-w-[min(42rem,100%)] ml-auto flex-row-reverse min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline">
                    <Icon name="person" size={16} className="text-on-surface-variant" />
                  </div>
                  <div className="bg-surface-container-high border border-primary/20 px-md py-sm rounded-xl rounded-tr-sm min-w-0 break-words">
                    <p className="text-[13px] leading-relaxed text-on-surface break-words">{m.message}</p>
                  </div>
                </div>
              )
            )
          )}
          {sending && (
            <div className="flex items-center gap-2 text-on-surface-variant text-[12px]">
              <Spinner size={12} /> Analyzing…
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="md:hidden px-3 pt-2 flex gap-2 overflow-x-auto">
          {PROMPTS.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => !sending && send(p.query)}
              className="shrink-0 px-3 py-2 rounded-full border border-outline bg-surface-container text-[12px] text-on-surface"
            >
              {p.label}
            </button>
          ))}
          {messages.length > 0 && (
            <button type="button" onClick={clear} className="shrink-0 px-3 py-2 rounded-full border border-outline text-[12px] text-on-surface-variant">
              Clear
            </button>
          )}
        </div>

        <div className="px-3 sm:px-md pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-sm border-t border-outline/60">
          <div className="glass-panel px-sm py-1 rounded-xl flex items-center gap-sm">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && submit()}
              placeholder="Type your financial query…"
              className="flex-1 bg-transparent border-none focus:ring-0 text-[13px] py-2 px-1 text-on-surface placeholder:text-on-surface-variant/40"
            />
            <button
              onClick={submit}
              disabled={!input.trim() || sending}
              className="w-9 h-9 bg-primary text-on-primary rounded-lg flex items-center justify-center hover:opacity-90 active:scale-95 transition-all disabled:opacity-40 shrink-0"
            >
              <Icon name="send" size={16} fill />
            </button>
          </div>
          <p className="mt-1.5 text-center text-[10px] text-on-surface-variant/40">
            Monetra can make mistakes. Verify critical financial data.
          </p>
        </div>
      </section>
    </div>
  );
}
