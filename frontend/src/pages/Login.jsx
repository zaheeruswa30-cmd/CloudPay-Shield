import { useState } from "react";
import { ArrowLeft, CheckCircle2, KeyRound, Loader2, LogIn, UserPlus } from "lucide-react";
import { api } from "../api";
import { useAuth, useToast } from "../context";
import { Field, PasswordInput, PasswordRules, passwordOk } from "../components/ui";
import { Logo } from "../components/Logo";

const USERNAME_RE = /^[A-Za-z0-9_.-]{3,32}$/;

function AuthLayout({ children, go }) {
  return (
    <div className="login-wrap">
      <div className="login-brand">
        <a href="#/" className="back-link small" onClick={(e) => { e.preventDefault(); go(""); }}><ArrowLeft size={14} /> Back to home</a>
        <Logo size={34} />
        <h1>Protect every salary change before it reaches payroll.</h1>
        <p>Each salary change is risk-scored on the server, approved by a different person, and recorded in a hash-chained audit trail.</p>
        <ul className="login-points">
          <li><span className="dot ok" /> Explainable risk scoring before any salary change</li>
          <li><span className="dot warn" /> Separation of duties and version-checked approvals</li>
          <li><span className="dot accent" /> TOTP MFA for privileged decisions</li>
        </ul>
        <p className="muted small">Local demo accounts are listed in the project README. All demo payroll data is fictional.</p>
      </div>
      <div className="login-card">{children}</div>
    </div>
  );
}

export function LoginPage({ go }) {
  const { acceptToken, sessionMessage } = useAuth();
  const toast = useToast();
  const [step, setStep] = useState("password"); // password | mfa
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submitLogin(e) {
    e.preventDefault();
    if (!username.trim() || !password) { setError("Enter your username and password."); return; }
    setBusy(true);
    setError("");
    try {
      const r = await api("/auth/login", { method: "POST", body: { username: username.trim(), password }, auth: false });
      setPassword("");
      if (r.mfa_required) {
        setMfaToken(r.mfa_token);
        setStep("mfa");
      } else {
        acceptToken(r);
        toast.success(`Signed in as ${r.user.username}`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitMfa(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api("/auth/mfa/login", { method: "POST", body: { mfa_token: mfaToken, code }, auth: false });
      acceptToken(r);
      toast.success(`Signed in with MFA as ${r.user.username}`);
    } catch (err) {
      setError(err.message);
      if (err.status === 401 && /expired|token/i.test(err.message)) setStep("password");
    } finally {
      setBusy(false);
      setCode("");
    }
  }

  return (
    <AuthLayout go={go}>
      {step === "password" ? (
        <>
          <div className="auth-head">
            <h2><LogIn size={20} /> Sign in</h2>
            <p className="small muted">Use your CloudPay Shield account.</p>
          </div>
          {sessionMessage && <div className="banner banner-info">{sessionMessage}</div>}
          {error && <div className="banner banner-crit" role="alert">{error}</div>}
          <form onSubmit={submitLogin} className="form" noValidate>
            <Field label="Username"><input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus /></Field>
            <Field label="Password"><PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
            <button className="btn btn-primary btn-block" disabled={busy}>
              {busy ? <><Loader2 size={15} className="spin" /> Signing in…</> : "Sign in"}
            </button>
          </form>
          <p className="small muted center">New here? <a href="#/register">Create an employee account</a></p>
        </>
      ) : (
        <form onSubmit={submitMfa} className="form">
          <div className="mfa-head"><KeyRound size={22} /><div><strong>Two-step verification</strong><p className="muted small">Enter the 6-digit code from your authenticator app, or a recovery code.</p></div></div>
          {error && <div className="banner banner-crit" role="alert">{error}</div>}
          <Field label="Verification code">
            <input className="code-input mono" inputMode="numeric" autoComplete="one-time-code" autoFocus maxLength={12} value={code} onChange={(e) => setCode(e.target.value.trim())} required />
          </Field>
          <button className="btn btn-primary btn-block" disabled={busy || code.length < 6}>{busy ? "Verifying…" : "Verify and sign in"}</button>
          <button type="button" className="btn btn-ghost btn-block" onClick={() => { setStep("password"); setMfaToken(""); setError(""); }}>Back</button>
        </form>
      )}
    </AuthLayout>
  );
}

export function RegisterPage({ go }) {
  const toast = useToast();
  const [form, setForm] = useState({ username: "", full_name: "", email: "", password: "", confirm: "" });
  const [touched, setTouched] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const blur = (k) => () => setTouched((t) => ({ ...t, [k]: true }));

  const errors = {
    username: !USERNAME_RE.test(form.username) ? "3–32 characters: letters, numbers, _ . -" : "",
    full_name: form.full_name.trim().length < 2 ? "Enter your full name." : "",
    email: form.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email) ? "Enter a valid email or leave it blank." : "",
    password: !passwordOk(form.password) ? "Password does not meet the policy yet." : "",
    confirm: form.confirm !== form.password ? "Passwords do not match." : "",
  };
  const valid = Object.values(errors).every((e) => !e);
  const show = (k) => (touched[k] || touched._submit) && errors[k];

  async function submit(e) {
    e.preventDefault();
    setTouched((t) => ({ ...t, _submit: true }));
    if (!valid) return;
    setBusy(true);
    setError("");
    try {
      await api("/auth/register", {
        method: "POST", auth: false,
        body: { username: form.username, full_name: form.full_name.trim(), email: form.email || null, password: form.password },
      });
      setDone(true);
      toast.success("Account created with the Employee role.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthLayout go={go}>
        <div className="done-panel">
          <CheckCircle2 size={36} className="ok-text" />
          <h2>Account created</h2>
          <p className="small muted">Your account <strong className="mono">{form.username}</strong> has the <strong>Employee</strong> role. If you need HR, manager or auditor access, sign in and request it from Account &amp; security. A security administrator reviews every request.</p>
          <button className="btn btn-primary btn-block" onClick={() => go("login")}>Continue to sign in</button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout go={go}>
      <div className="auth-head">
        <h2><UserPlus size={20} /> Create account</h2>
        <p className="small muted">Public sign-up creates an <strong>Employee</strong> account only. Privileged roles are granted through a reviewed access request.</p>
      </div>
      {error && <div className="banner banner-crit" role="alert">{error}</div>}
      <form onSubmit={submit} className="form" noValidate>
        <Field label="Username" error={show("username")}><input autoComplete="username" value={form.username} onChange={set("username")} onBlur={blur("username")} maxLength={32} /></Field>
        <Field label="Full name" error={show("full_name")}><input autoComplete="name" value={form.full_name} onChange={set("full_name")} onBlur={blur("full_name")} /></Field>
        <Field label="Email (optional)" error={show("email")}><input type="email" autoComplete="email" value={form.email} onChange={set("email")} onBlur={blur("email")} /></Field>
        <Field label="Password" error={show("password")}>
          <PasswordInput autoComplete="new-password" value={form.password} onChange={set("password")} onBlur={blur("password")} />
        </Field>
        <PasswordRules value={form.password} />
        <Field label="Confirm password" error={show("confirm")}>
          <PasswordInput autoComplete="new-password" value={form.confirm} onChange={set("confirm")} onBlur={blur("confirm")} />
        </Field>
        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy ? <><Loader2 size={15} className="spin" /> Creating…</> : "Create employee account"}
        </button>
      </form>
      <p className="small muted center">Already have an account? <a href="#/login">Sign in</a></p>
    </AuthLayout>
  );
}
