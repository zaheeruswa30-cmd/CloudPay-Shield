import { useState } from "react";
import {
  ArrowRight, BrainCircuit, CheckCircle2, ClipboardCheck, Database, FileSearch, Fingerprint, GitCompareArrows,
  KeyRound, Link2, Lock, Menu, Scale, ShieldAlert, ShieldCheck, UserCheck, Users, X,
} from "lucide-react";
import { Logo } from "../components/Logo";
import { useAuth } from "../context";

const FEATURES = [
  { icon: BrainCircuit, title: "Explainable risk scoring", body: "Every salary change gets a 0–100 score built from named indicators, so reviewers can see why it was flagged." },
  { icon: UserCheck, title: "Independent approval", body: "HR submits and a different payroll manager decides. The salary only changes after a manager approves." },
  { icon: KeyRound, title: "MFA for privileged actions", body: "Approvals and admin changes need TOTP multi-factor authentication, with recovery codes and lockout." },
  { icon: Fingerprint, title: "Tamper-evident audit trail", body: "Every action is written to a SHA-256 hash chain that auditors can verify from the browser." },
  { icon: GitCompareArrows, title: "Stale-update protection", body: "Version checks block a request from overwriting a salary that changed after it was prepared." },
  { icon: Database, title: "Safe data import", body: "CSV files are validated and staged for review. Nothing is written to payroll automatically." },
];

const STEPS = [
  { icon: ClipboardCheck, title: "HR submits", body: "HR picks an employee, enters the proposed salary and a business reason. The percentage change is calculated automatically." },
  { icon: ShieldAlert, title: "Backend assesses risk", body: "The server checks policy rules, request patterns and salary history, then stores an explained risk score." },
  { icon: Users, title: "Manager reviews", body: "A different person reviews the evidence, records a reason and approves or rejects using MFA." },
  { icon: Link2, title: "Applied and audited", body: "Only an approval updates the salary. Each step is added to the hash-chained audit log." },
];

const SIGNALS = [
  { icon: Scale, title: "Policy rules", items: ["Increase and decrease thresholds", "Salary floor and ceiling", "Missing or vague reasons", "Self-service and permission checks"] },
  { icon: FileSearch, title: "Historical patterns", items: ["Robust z-score against peer changes", "Repeated requests for one employee", "Off-hours submissions", "Clearly marked when history is too thin"] },
  { icon: BrainCircuit, title: "Explainable output", items: ["Score 0–100 with Low to Critical levels", "Each indicator shows its points", "Recommended next action", "Flags start a review, never an accusation"] },
];

export default function Landing({ go }) {
  const { user } = useAuth();
  const [menu, setMenu] = useState(false);
  const scrollTo = (id) => { setMenu(false); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); };
  const nav = [["features", "Features"], ["how", "How it works"], ["ai", "Anomaly detection"], ["security", "Security"]];

  return (
    <div className="landing">
      <header className="l-nav">
        <div className="l-container l-nav-inner">
          <a href="#/" aria-label="CloudPay Shield home"><Logo size={28} /></a>
          <nav className={`l-links ${menu ? "open" : ""}`} aria-label="Landing">
            {nav.map(([id, label]) => <button key={id} onClick={() => scrollTo(id)}>{label}</button>)}
            <span className="l-nav-cta">
              {user ? (
                <a className="btn btn-primary btn-sm" href="#/overview">Open console</a>
              ) : (
                <>
                  <a className="btn btn-ghost btn-sm" href="#/login">Sign in</a>
                  <a className="btn btn-primary btn-sm" href="#/register">Create account</a>
                </>
              )}
            </span>
          </nav>
          <button className="icon-btn l-burger" onClick={() => setMenu((m) => !m)} aria-label="Toggle menu">{menu ? <X size={20} /> : <Menu size={20} />}</button>
        </div>
      </header>

      <section className="l-hero">
        <div className="l-container l-hero-grid">
          <div>
            <span className="l-eyebrow"><ShieldCheck size={14} /> Payroll integrity platform</span>
            <h1>Stop unauthorised salary changes <span className="accent-text">before they reach payroll.</span></h1>
            <p className="l-lead">CloudPay Shield risk-scores every salary change request, sends unusual ones for human review, requires independent approval, and records everything in a verifiable audit trail.</p>
            <div className="l-cta">
              {user ? <a className="btn btn-primary btn-lg" href="#/overview">Open your console <ArrowRight size={16} /></a> : (
                <>
                  <a className="btn btn-primary btn-lg" href="#/login">Sign in <ArrowRight size={16} /></a>
                  <a className="btn btn-ghost btn-lg" href="#/register">Create an employee account</a>
                </>
              )}
            </div>
            <ul className="l-checks small">
              <li><CheckCircle2 size={15} /> Salary updates only after manager approval</li>
              <li><CheckCircle2 size={15} /> Flags mean "review", not "fraud"</li>
            </ul>
          </div>
          <figure className="l-shot">
            <img src="/dashboard-preview.png" alt="CloudPay Shield security dashboard showing risk score gauge, request status and risk distribution charts" width="1440" height="900" />
            <figcaption className="tiny muted">Actual application screen with fictional demo data.</figcaption>
          </figure>
        </div>
      </section>

      <section className="l-section" id="problem">
        <div className="l-container l-problem">
          <div>
            <span className="l-eyebrow warn"><ShieldAlert size={14} /> The problem</span>
            <h2>One edited salary field can go unnoticed for months.</h2>
          </div>
          <div className="l-problem-list">
            <p>In many payroll tools, whoever can edit a record can change pay directly. Mistakes, insider abuse and compromised accounts look the same in the database: a new number.</p>
            <ul>
              <li><X size={15} /> No second person checks large or unusual changes</li>
              <li><X size={15} /> Reviewers can't see why a change looks unusual</li>
              <li><X size={15} /> Logs can be edited, so nobody can prove what happened</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="l-section alt" id="features">
        <div className="l-container">
          <div className="l-head"><span className="l-eyebrow">Features</span><h2>Controls built into every salary change</h2></div>
          <div className="l-features">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <article key={f.title} className="l-card">
                  <span className="l-icon"><Icon size={20} /></span>
                  <h3>{f.title}</h3>
                  <p className="small muted">{f.body}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="l-section" id="how">
        <div className="l-container">
          <div className="l-head"><span className="l-eyebrow">How it works</span><h2>From request to audited payroll update</h2></div>
          <ol className="l-steps">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              return (
                <li key={s.title} className="l-step">
                  <span className="l-step-num mono">{String(i + 1).padStart(2, "0")}</span>
                  <Icon size={22} className="accent-text" />
                  <h3>{s.title}</h3>
                  <p className="small muted">{s.body}</p>
                </li>
              );
            })}
          </ol>
        </div>
      </section>

      <section className="l-section alt" id="ai">
        <div className="l-container">
          <div className="l-head">
            <span className="l-eyebrow">AI-assisted anomaly detection</span>
            <h2>A hybrid model that explains itself</h2>
            <p className="muted">CloudPay Shield combines policy rules with statistics from your own salary history. The result is a risk score that helps a reviewer decide what to check. It is not a validated fraud probability, and the app says so when there is not enough history to compare against.</p>
          </div>
          <div className="l-signals">
            {SIGNALS.map((s) => {
              const Icon = s.icon;
              return (
                <article key={s.title} className="l-card">
                  <span className="l-icon"><Icon size={20} /></span>
                  <h3>{s.title}</h3>
                  <ul className="l-list small">{s.items.map((i) => <li key={i}><CheckCircle2 size={14} /> {i}</li>)}</ul>
                </article>
              );
            })}
          </div>
          <div className="l-levels" aria-label="Risk levels">
            {[["Low", "0–24", "Standard review"], ["Medium", "25–49", "Check the reason"], ["High", "50–74", "Enhanced review"], ["Critical", "75–100", "Investigate first"]].map(([l, r, d]) => (
              <div key={l} className={`l-level lv-${l.toLowerCase()}`}><strong>{l}</strong><span className="mono small">{r}</span><span className="tiny muted">{d}</span></div>
            ))}
          </div>
        </div>
      </section>

      <section className="l-section" id="security">
        <div className="l-container l-security">
          <div>
            <span className="l-eyebrow">Security</span>
            <h2>Enforced on the server, not just hidden in the UI</h2>
            <p className="muted">Every rule is checked by the API, so hiding a button is never the only control.</p>
          </div>
          <ul className="l-sec-list">
            <li><Lock size={18} /><div><strong>Role-based access control</strong><span className="small muted">Employee, HR, manager, auditor and security admin roles. Public sign-up creates employees only.</span></div></li>
            <li><UserCheck size={18} /><div><strong>Separation of duties</strong><span className="small muted">Self-approval and duplicate decisions are blocked by the backend.</span></div></li>
            <li><KeyRound size={18} /><div><strong>TOTP MFA and lockouts</strong><span className="small muted">Required for managers and admins. Codes can't be replayed.</span></div></li>
            <li><Fingerprint size={18} /><div><strong>Hash-chained audit log</strong><span className="small muted">Detects edited, removed or reordered events. Its limits are stated in the app.</span></div></li>
          </ul>
        </div>
      </section>

      <section className="l-section l-final">
        <div className="l-container l-final-inner">
          <h2>Ready to review salary changes safely?</h2>
          <div className="l-cta">
            <a className="btn btn-primary btn-lg" href={user ? "#/overview" : "#/login"}>{user ? "Open console" : "Sign in"} <ArrowRight size={16} /></a>
            {!user && <a className="btn btn-ghost btn-lg" href="#/register">Create account</a>}
          </div>
        </div>
      </section>

      <footer className="l-footer">
        <div className="l-container l-footer-inner">
          <Logo size={22} />
          <span className="tiny muted">Hackathon build · all employee and payroll data in this demo is fictional.</span>
          <nav className="tiny">
            <button onClick={() => scrollTo("features")}>Features</button>
            <button onClick={() => scrollTo("security")}>Security</button>
            <a href="#/login">Sign in</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
