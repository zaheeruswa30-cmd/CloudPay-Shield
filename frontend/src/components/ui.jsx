import { AlertOctagon, Eye, EyeOff, Inbox, Loader2, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

export const RISK_COLORS = {
  Low: "#22c55e",
  Medium: "#f5b301",
  High: "#fb7a24",
  Critical: "#f43f5e",
};

export function RiskBadge({ level, score }) {
  if (!level) return <span className="badge">—</span>;
  return (
    <span className={`badge risk-${level.toLowerCase()}`}>
      <span className="dot" aria-hidden />
      {level}
      {score !== undefined && score !== null && <span className="mono"> · {score}</span>}
    </span>
  );
}

export function StatusBadge({ status }) {
  return <span className={`badge status-${status}`}>{status}</span>;
}

export function Panel({ title, icon: Icon, actions, children, className = "", subtitle }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-head">
          <div>
            <h2>
              {Icon && <Icon size={16} aria-hidden />} {title}
            </h2>
            {subtitle && <p className="muted small">{subtitle}</p>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, icon: Icon, tone = "accent", hint }) {
  return (
    <div className={`stat tone-${tone}`}>
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        {Icon && <Icon size={18} aria-hidden />}
      </div>
      <div className="stat-value mono">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Loading({ label = "Loading…" }) {
  return (
    <div className="state">
      <Loader2 className="spin" size={20} aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function SkeletonRows({ rows = 4 }) {
  return (
    <div className="skeleton-wrap" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" />
      ))}
    </div>
  );
}

export function Empty({ title = "Nothing here yet", children }) {
  return (
    <div className="state empty">
      <Inbox size={22} aria-hidden />
      <div>
        <strong>{title}</strong>
        {children && <p className="muted small">{children}</p>}
      </div>
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  const status = error.status;
  const message =
    status === 403 ? "Your role does not have access to this information." : error.message || "Something went wrong.";
  return (
    <div className="state error" role="alert">
      <AlertOctagon size={20} aria-hidden />
      <span>{message}</span>
      {onRetry && (
        <button className="btn btn-ghost btn-sm" onClick={onRetry}>
          <RefreshCw size={14} /> Retry
        </button>
      )}
    </div>
  );
}

export function Drawer({ open, onClose, title, children }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="drawer-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title}>
        <header className="drawer-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close details">
            <X size={18} />
          </button>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

export function Field({ label, hint, children, error }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && !error && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </label>
  );
}

/** Centered modal dialog with focus on open and Escape to close. */
export function Modal({ open, onClose, title, children, footer, tone = "default", width = 480 }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className={`modal tone-${tone}`} role="dialog" aria-modal="true" aria-label={title} style={{ maxWidth: width }}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close dialog"><X size={18} /></button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  );
}

/** Confirmation dialog: the action only runs after an explicit second click. */
export function ConfirmDialog({ open, title, children, confirmLabel = "Confirm", tone = "default", busy, onConfirm, onCancel, disabled }) {
  return (
    <Modal open={open} onClose={busy ? undefined : onCancel} title={title} tone={tone}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onCancel} disabled={busy}>Cancel</button>
          <button className={`btn ${tone === "danger" ? "btn-crit" : tone === "ok" ? "btn-ok" : "btn-primary"}`}
            onClick={onConfirm} disabled={busy || disabled} autoFocus>
            {busy ? <Loader2 size={15} className="spin" /> : null} {confirmLabel}
          </button>
        </>
      }>
      {children}
    </Modal>
  );
}

/** Password input with a show/hide toggle. */
export function PasswordInput({ value, onChange, autoComplete = "current-password", ...rest }) {
  const [show, setShow] = useState(false);
  return (
    <div className="pw-wrap">
      <input type={show ? "text" : "password"} value={value} onChange={onChange} autoComplete={autoComplete} {...rest} />
      <button type="button" className="pw-toggle" onClick={() => setShow((s) => !s)}
        aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}>
        {show ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}

/** Password strength checklist matching the backend policy. */
export function PasswordRules({ value }) {
  const rules = [
    { ok: value.length >= 12, label: "12+ characters" },
    { ok: [/[a-z]/, /[A-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter((r) => r.test(value)).length >= 3, label: "3 of: lowercase, uppercase, digit, symbol" },
  ];
  return (
    <ul className="pw-rules" aria-label="Password requirements">
      {rules.map((r) => <li key={r.label} className={r.ok ? "ok" : ""}><span className="dot" />{r.label}</li>)}
    </ul>
  );
}

export const passwordOk = (v) =>
  v.length >= 12 && [/[a-z]/, /[A-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter((r) => r.test(v)).length >= 3;
