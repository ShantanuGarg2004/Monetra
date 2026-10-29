import { useState } from "react";
import { createPortal } from "react-dom";
import Button from "../components/Button";
import { TextField } from "../components/Field";
import { apiFetch } from "../config/api";
import Icon from "../components/Icon";
import Reveal from "../components/Reveal";
import dashboardShot from "../assets/platform-dashboard.png";
import advisoryShot from "../assets/platform-advisory.png";
import goalsShot from "../assets/platform-goals.png";

const featureCards = [
  {
    icon: "query_stats",
    eyebrow: "01 / See clearly",
    title: "One score for your whole financial life.",
    body: "A calm, contextual read on your financial health — with the levers that matter most surfaced first.",
    tone: "gold",
  },
  {
    icon: "auto_graph",
    eyebrow: "02 / Plan forward",
    title: "Make ambitious goals feel measurable.",
    body: "Model a home, a sabbatical, or financial freedom against the reality of your cash flow.",
    tone: "emerald",
  },
  {
    icon: "smart_toy",
    eyebrow: "03 / Ask anything",
    title: "An advisor that speaks human.",
    body: "Get thoughtful guidance on demand — grounded in your numbers, never in noise or jargon.",
    tone: "lilac",
  },
];

function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <div className="brand-mark"><span /></div>
      <div>
        <div className="font-display text-[15px] font-bold tracking-tight text-white">FinPilot <span className="text-gold">AI</span></div>
        <div className="text-[9px] font-semibold uppercase tracking-[0.22em] text-muted">Premium wealth pilot</div>
      </div>
    </div>
  );
}

function MiniChart() {
  return (
    <div className="mini-chart" aria-label="Illustrative rising financial health chart">
      <div className="chart-grid" />
      <svg viewBox="0 0 280 120" role="img" aria-hidden="true">
        <defs>
          <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22c995" stopOpacity=".32" />
            <stop offset="100%" stopColor="#22c995" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M0 103 C22 99 27 83 50 87 S78 71 96 76 S121 61 140 66 S164 42 184 48 S208 27 230 32 S256 12 280 9 V120 H0Z" fill="url(#chartFill)" />
        <path d="M0 103 C22 99 27 83 50 87 S78 71 96 76 S121 61 140 66 S164 42 184 48 S208 27 230 32 S256 12 280 9" fill="none" stroke="#22c995" strokeWidth="3" strokeLinecap="round" />
        <circle cx="280" cy="9" r="5" fill="#22c995" stroke="#0b1211" strokeWidth="3" />
      </svg>
      <div className="flex items-center justify-between pt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted"><span>Today</span><span>Next 12 months</span></div>
    </div>
  );
}

function AuthPanel({ mode, setMode, onSignedIn, onClose }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  function switchMode(next) {
    setMode(next);
    setError("");
    setNotice("");
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (mode === "signup" && password !== confirm) {
      setError("Confirm password must match password.");
      return;
    }
    setLoading(true);
    try {
      if (mode === "forgot") {
        const body = await apiFetch("/auth/forgot-password", {
          method: "POST",
          body: JSON.stringify({ email }),
        });
        setNotice(body.message);
        return;
      }
      const path = mode === "signup" ? "/auth/signup" : "/auth/login";
      const body = mode === "signup" ? { email, password, confirm_password: confirm } : { email, password };
      onSignedIn(await apiFetch(path, { method: "POST", body: JSON.stringify(body) }));
    } catch (err) {
      setError(err.message || "Email or password is incorrect.");
    } finally {
      setLoading(false);
    }
  }

  return createPortal(
    <div className="auth-backdrop" role="dialog" aria-modal="true" aria-label={mode === "signup" ? "Create your account" : "Sign in"} onClick={onClose}>
      <div className="auth-panel" onClick={(event) => event.stopPropagation()}>
        <button className="auth-close" onClick={onClose} aria-label="Close"><Icon name="close" size={20} /></button>
        <div className="mb-7"><BrandMark /><h2 className="mt-8 font-display text-3xl font-bold text-white">{mode === "signup" ? "Build your money map." : mode === "forgot" ? "Reset your password." : "Welcome back."}</h2><p className="mt-2 text-sm leading-6 text-muted">{mode === "signup" ? "Your financial co-pilot is ready when you are." : mode === "forgot" ? "Enter the email for the account." : "Pick up where your financial clarity left off."}</p></div>
        <form onSubmit={submit} className="space-y-4">
          <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          {mode !== "forgot" && <TextField label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete={mode === "signup" ? "new-password" : "current-password"} />}
          {mode === "signup" && <p className="text-[12px] leading-5 text-muted">Password must be at least 12 characters.</p>}
          {mode === "signup" && <TextField label="Confirm password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required autoComplete="new-password" />}
          {mode === "signin" && (
            <button type="button" className="text-[13px] font-semibold text-gold hover:text-white" onClick={() => switchMode("forgot")}>Forgot password?</button>
          )}
          {error && <p className="text-[13px] text-error">{error}</p>}
          {notice && <p className="text-sm leading-6 text-gold">{notice}</p>}
          <Button type="submit" loading={loading} className="w-full">{mode === "signup" ? "Create your account" : mode === "forgot" ? "Send reset link" : "Sign in"}</Button>
        </form>
        <button type="button" className="mt-5 text-[13px] font-semibold text-gold hover:text-white" onClick={() => switchMode(mode === "signin" ? "signup" : "signin")}>
          {mode === "signin" ? "New to FinPilot? Create an account" : "Already have an account? Sign in"}
        </button>
      </div>
    </div>,
    document.body,
  );
}

export default function LoginPage({ onSignedIn }) {
  const [showAuth, setShowAuth] = useState(false);
  const [mode, setMode] = useState("signup");

  function openAuth(nextMode = "signup") {
    setMode(nextMode);
    setShowAuth(true);
  }

  return (
    <div className="landing-page">
      <header className="landing-nav">
        <a href="#top" aria-label="FinPilot AI home"><BrandMark /></a>
        <nav className="hidden items-center gap-8 md:flex" aria-label="Primary navigation">
          <a href="#platform">Platform</a><a href="#how-it-works">How it works</a><a href="#principles">Our approach</a>
        </nav>
        <div className="flex items-center gap-3"><button className="nav-login" onClick={() => openAuth("signin")}>Sign in</button><button className="nav-cta" onClick={() => openAuth("signup")}>Get started <Icon name="arrow_forward" size={16} /></button></div>
      </header>

      <main id="top">
        <section className="hero-section">
          <div className="hero-grid-lines" />
          <div className="hero-copy">
            <div className="eyebrow"><span className="eyebrow-dot" /> Your wealth, navigated by AI</div>
            <h1>Make your money<br /><span>make more sense.</span></h1>
            <p className="hero-lede">FinPilot brings your financial picture into focus — so you can make confident decisions today and build the life you actually want tomorrow.</p>
            <div className="hero-actions"><button className="button-gold" onClick={() => openAuth("signup")}>Start your financial map <Icon name="arrow_forward" size={18} /></button><a className="watch-link" href="#platform"><span className="play-dot"><Icon name="play_arrow" size={15} fill /></span> See the platform</a></div>
            <div className="hero-proof"><div className="avatar-stack"><span>AS</span><span>RN</span><span>MK</span></div><div><strong>Built for real life.</strong><small>Clarity for the decisions that matter.</small></div></div>
          </div>
          <div className="hero-visual">
            <div className="orbital orbital-one" /><div className="orbital orbital-two" />
            <div className="hero-dashboard-card">
              <div className="card-topline"><span className="status-pill"><i /> Live financial picture</span><Icon name="more_horiz" size={20} className="text-muted" /></div>
              <div className="hero-score-row"><div><span className="metric-label">Financial health</span><div className="score-number">82<span>/100</span></div><div className="score-delta"><Icon name="trending_up" size={14} /> +8.4% this quarter</div></div><div className="score-ring"><div><b>82</b><small>healthy</small></div></div></div>
              <MiniChart />
              <div className="hero-stats"><div><span>Monthly surplus</span><b>₹40,000</b></div><div><span>Savings rate</span><b>26.7%</b></div><div><span>Next milestone</span><b>2030</b></div></div>
            </div>
            <div className="floating-insight"><span className="insight-icon"><Icon name="auto_awesome" size={18} fill /></span><div><b>One small shift</b><p>could add ₹4.8L to your goal.</p></div><Icon name="arrow_forward" size={16} className="text-gold" /></div>
          </div>
        </section>

        <Reveal as="section" className="trust-strip"><span>BUILT FOR THE FULL PICTURE</span><div><Icon name="shield" size={18} /> Private by design</div><div><Icon name="visibility" size={18} /> Clear by default</div><div><Icon name="lock" size={18} /> Yours, always</div></Reveal>

        <Reveal as="section" className="intro-section" id="how-it-works"><div className="section-kicker">A better relationship with money</div><div className="intro-grid"><h2>Less guesswork.<br /><em>More good decisions.</em></h2><p>Most financial tools show you what happened. FinPilot helps you understand what to do next — with a clear view of your health, your goals, and the trade-offs in between.</p></div></Reveal>

        <section className="feature-section" id="principles"><Reveal as="div" className="feature-grid reveal-cards">{featureCards.map((card) => <article className={`feature-card ${card.tone}`} key={card.title}><div className="feature-icon"><Icon name={card.icon} size={22} fill /></div><div className="feature-eyebrow">{card.eyebrow}</div><h3>{card.title}</h3><p>{card.body}</p><span className="feature-line" /></article>)}</Reveal></section>

        <section className="platform-section" id="platform">
          <Reveal className="platform-heading"><div><div className="section-kicker">The FinPilot cockpit</div><h2>Every signal.<br /><em>One calm place.</em></h2></div><p>Designed to feel less like a spreadsheet and more like a trusted second opinion.</p></Reveal>
          <Reveal className="platform-showcase"><div className="showcase-copy"><span className="showcase-number">01</span><h3>Know where you stand.</h3><p>Your health score turns the complicated into something you can act on. See your strengths, your blind spots, and your next best move.</p><button className="text-link" onClick={() => openAuth("signup")}>Explore your dashboard <Icon name="arrow_forward" size={16} /></button></div><div className="showcase-image"><img src={dashboardShot} alt="FinPilot AI onboarding profile dashboard" /></div></Reveal>
          <Reveal className="platform-collage"><div className="collage-image advisory"><img src={advisoryShot} alt="FinPilot AI advisory report" /></div><div className="collage-copy"><span className="showcase-number">02</span><h3>Turn insight into momentum.</h3><p>Personalized advisory, goal simulations, and an AI chat that remembers the context — all designed around your version of a good life.</p><div className="collage-pills"><span>AI advisory</span><span>Goal simulator</span><span>Personal chat</span></div></div><div className="collage-image goals"><img src={goalsShot} alt="FinPilot AI goals simulator" /></div></Reveal>
        </section>

        <section className="principles-section"><Reveal className="principles-card"><div><div className="section-kicker">Our point of view</div><h2>Financial confidence<br /><em>is a feeling.</em></h2></div><div className="principles-list"><div><span>01</span><p><b>Context over noise.</b> Your money is personal. Advice should be too.</p></div><div><span>02</span><p><b>Progress over perfection.</b> The best plan is the one you can keep.</p></div><div><span>03</span><p><b>Clarity over complexity.</b> Good guidance should leave you feeling lighter.</p></div></div></Reveal></section>

        <Reveal as="section" className="final-cta"><div className="cta-glow" /><div className="section-kicker">Your next chapter starts here</div><h2>Ready to feel more<br /><em>in control?</em></h2><p>Set up your financial map in minutes. Your future self will thank you.</p><button className="button-gold" onClick={() => openAuth("signup")}>Create your free account <Icon name="arrow_forward" size={18} /></button></Reveal>
      </main>
      <footer className="landing-footer"><BrandMark /><span>© 2026 FinPilot AI. Built for a clearer tomorrow.</span><a href="#top">Back to top <Icon name="north" size={14} /></a></footer>
      {showAuth && <AuthPanel mode={mode} setMode={setMode} onSignedIn={onSignedIn} onClose={() => setShowAuth(false)} />}
    </div>
  );
}
