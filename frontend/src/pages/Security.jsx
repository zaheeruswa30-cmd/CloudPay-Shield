import { useState } from "react";
import { BadgeCheck, KeyRound, Lock, QrCode, ShieldCheck, ShieldOff, UserCircle2, UserPlus } from "lucide-react";
import { api, fmtDate, ROLE_LABEL } from "../api";
import { useApi, useAuth, useToast } from "../context";
import { ConfirmDialog, Empty, Field, Panel, PasswordInput, PasswordRules, passwordOk, SkeletonRows } from "../components/ui";

export default function Security({ refreshKey }) {
  const { user, acceptToken } = useAuth();
  const toast = useToast();
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true);
    try {
      setSetup(await api("/auth/mfa/setup", { method: "POST" }));
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function enable(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api("/auth/mfa/enable", { method: "POST", body: { code } });
      acceptToken(r);
      setRecovery(r.recovery_codes);
      setSetup(null);
      toast.success("MFA enabled. Your session is now MFA-verified.");
    } catch (e2) {
      toast.error(e2.message);
    } finally {
      setBusy(false);
      setCode("");
    }
  }

  async function disable(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api("/auth/mfa/disable", { method: "POST", body: { code } });
      acceptToken(r);
      toast.success("MFA disabled.");
    } catch (e2) {
      toast.error(e2.message);
    } finally {
      setBusy(false);
      setCode("");
    }
  }

  return (
    <div className="page">
      <ProfileCard user={user} />
      <div className="grid-2 align-start">
      <Panel title="Multi-factor authentication" icon={KeyRound} subtitle="TOTP codes from Google Authenticator, Microsoft Authenticator, Authy, 1Password…">
        <div className={`mfa-status ${user.mfa_enabled ? "on" : "off"}`}>
          {user.mfa_enabled ? <ShieldCheck size={26} /> : <ShieldOff size={26} />}
          <div>
            <strong>{user.mfa_enabled ? "MFA is enabled" : "MFA is not enabled"}</strong>
            <p className="small muted">
              {user.mfa_enabled
                ? `This session is ${user.mfa_verified_session ? "MFA-verified" : "not MFA-verified"}. ${user.recovery_codes_remaining} recovery codes left.`
                : user.mfa_required_for_role
                  ? `Required for your role: ${user.role === "admin" ? "admin actions" : "approvals and rejections"} are blocked until you enrol.`
                  : "Recommended for every account."}
            </p>
          </div>
        </div>

        {!user.mfa_enabled && !setup && (
          <button className="btn btn-primary" onClick={start} disabled={busy}><QrCode size={16} /> Set up authenticator app</button>
        )}

        {setup && (
          <form className="form" onSubmit={enable}>
            <ol className="steps">
              <li>Open your authenticator app and scan this QR code.</li>
              <li>Enter the 6-digit code it shows to confirm.</li>
            </ol>
            <div className="qr" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} aria-label="MFA QR code" />
            <details className="small">
              <summary>Can’t scan? Enter the key manually</summary>
              <p className="mono key">{setup.manual_entry_key}</p>
              <p className="muted tiny">Shown only during setup. Do not share or screenshot it.</p>
            </details>
            <Field label="6-digit code">
              <input className="code-input mono" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} required />
            </Field>
            <button className="btn btn-primary" disabled={busy || code.length !== 6}>Verify and enable</button>
          </form>
        )}

        {user.mfa_enabled && !["manager", "admin"].includes(user.role) && (
          <form className="form" onSubmit={disable}>
            <Field label="Disable MFA" hint="Enter a current code or a recovery code.">
              <input className="mono" maxLength={12} value={code} onChange={(e) => setCode(e.target.value.trim())} />
            </Field>
            <button className="btn btn-ghost" disabled={busy || code.length < 6}>Disable MFA</button>
          </form>
        )}
        {user.mfa_enabled && ["manager", "admin"].includes(user.role) && (
          <p className="small muted"><Lock size={13} /> MFA cannot be turned off for the {ROLE_LABEL[user.role]} role.</p>
        )}
      </Panel>

      <Panel title="Recovery" icon={ShieldCheck}>
        {recovery ? (
          <>
            <div className="banner banner-warn">Save these one-time recovery codes now. They will not be shown again.</div>
            <ul className="recovery mono">{recovery.map((c) => <li key={c}>{c}</li>)}</ul>
          </>
        ) : (
          <div className="small">
            <p>Lost your device? Use a recovery code at the sign-in verification step. Each code works once.</p>
            <p className="muted">Lost both your device and your recovery codes? Ask a security administrator to reset MFA from the Users &amp; access page. They must record a reason, and the reset is written to the audit trail.</p>
            <p className="muted">Verification is limited to 5 wrong codes, followed by a 5-minute lock. Used codes cannot be replayed.</p>
          </div>
        )}
      </Panel>
      </div>
      <div className="grid-2 align-start">
        <ChangePassword />
        {user.role !== "admin" && <AccessRequests user={user} refreshKey={refreshKey} />}
      </div>
    </div>
  );
}

function ProfileCard({ user }) {
  return (
    <Panel title="Profile" icon={UserCircle2}>
      <dl className="kv kv-row">
        <div><dt>Name</dt><dd>{user.full_name}</dd></div>
        <div><dt>Username</dt><dd className="mono">{user.username}</dd></div>
        <div><dt>Email</dt><dd>{user.email || "—"}</dd></div>
        <div><dt>Role</dt><dd><span className={`role-pill role-${user.role}`}>{user.role_label || ROLE_LABEL[user.role]}</span></dd></div>
        <div><dt>Linked payroll record</dt><dd className="mono">{user.employee_code || "None"}</dd></div>
        <div><dt>Member since</dt><dd>{fmtDate(user.created_at)}</dd></div>
      </dl>
    </Panel>
  );
}

function ChangePassword() {
  const { endSession } = useAuth();
  const toast = useToast();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const valid = cur && passwordOk(next) && next === confirm && next !== cur;

  async function submit(e) {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError("");
    try {
      await api("/auth/change-password", { method: "POST", body: { current_password: cur, new_password: next } });
      toast.success("Password changed. Please sign in with your new password.");
      endSession("Password changed. Sign in with your new password.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Change password" icon={Lock} subtitle="You will be signed out of this session afterwards.">
      {error && <div className="banner banner-crit" role="alert">{error}</div>}
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Current password"><PasswordInput value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
        <Field label="New password"><PasswordInput autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
        <PasswordRules value={next} />
        <Field label="Confirm new password" error={confirm && confirm !== next ? "Passwords do not match." : null}>
          <PasswordInput autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </Field>
        <button className="btn btn-primary" disabled={busy || !valid}>{busy ? "Saving…" : "Change password"}</button>
      </form>
    </Panel>
  );
}

const REQUESTABLE = [
  { role: "hr", label: "HR officer", desc: "Submit salary change requests and import payroll data" },
  { role: "manager", label: "Payroll manager", desc: "Approve or reject salary changes (MFA required)" },
  { role: "auditor", label: "Auditor", desc: "Read-only access to requests, anomalies and the audit trail" },
];

function AccessRequests({ user, refreshKey }) {
  const toast = useToast();
  const mine = useApi("/access-requests/mine", [refreshKey]);
  const [role, setRole] = useState("");
  const [why, setWhy] = useState("");
  const [busy, setBusy] = useState(false);
  const [cancelId, setCancelId] = useState(null);
  const pending = (mine.data || []).find((a) => a.status === "pending");
  const options = REQUESTABLE.filter((r) => r.role !== user.role);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/access-requests", { method: "POST", body: { requested_role: role, justification: why.trim() } });
      toast.success("Access request sent to the security administrators.");
      setRole(""); setWhy("");
      mine.reload();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    setBusy(true);
    try {
      await api(`/access-requests/${cancelId}/cancel`, { method: "POST" });
      toast.info("Access request cancelled.");
      mine.reload();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
      setCancelId(null);
    }
  }

  return (
    <Panel title="Request a different role" icon={UserPlus} subtitle="Privileged roles are never self-assigned. A security administrator reviews each request.">
      {mine.loading && !mine.data ? <SkeletonRows /> : pending ? (
        <div className="banner banner-info">
          <BadgeCheck size={16} />
          <div>
            <strong>Pending: {pending.requested_role_label}</strong> · sent {fmtDate(pending.created_at)}
            <p className="small muted">“{pending.justification}”</p>
            <button className="btn btn-ghost btn-sm" onClick={() => setCancelId(pending.id)}>Cancel request</button>
          </div>
        </div>
      ) : (
        <form className="form" onSubmit={submit}>
          <div className="role-options" role="radiogroup" aria-label="Requested role">
            {options.map((o) => (
              <label key={o.role} className={`role-option ${role === o.role ? "active" : ""}`}>
                <input type="radio" name="role" value={o.role} checked={role === o.role} onChange={() => setRole(o.role)} />
                <strong>{o.label}</strong><span className="small muted">{o.desc}</span>
              </label>
            ))}
          </div>
          <Field label="Business justification" hint="At least 20 characters. Include your team, manager and why you need this access."
            error={why && why.trim().length < 20 ? `${20 - why.trim().length} more characters needed.` : null}>
            <textarea rows={3} value={why} onChange={(e) => setWhy(e.target.value)} maxLength={1000} />
          </Field>
          <button className="btn btn-primary" disabled={busy || !role || why.trim().length < 20}>Send access request</button>
        </form>
      )}
      {(mine.data || []).filter((a) => a.status !== "pending").length > 0 && (
        <>
          <h3 className="h3">Previous requests</h3>
          <ul className="req-mini">
            {mine.data.filter((a) => a.status !== "pending").map((a) => (
              <li key={a.id}><div className="req-row">
                <span>{a.requested_role_label}</span>
                <span className={`status-pill s-${a.status}`}>{a.status}</span>
                <span className="small muted">{fmtDate(a.decided_at || a.created_at)}</span>
                {a.decision_reason && <span className="small muted">“{a.decision_reason}”</span>}
              </div></li>
            ))}
          </ul>
        </>
      )}
      {!mine.loading && (mine.data || []).length === 0 && !pending && <Empty title="No access requests yet" />}
      <ConfirmDialog open={!!cancelId} title="Cancel access request?" confirmLabel="Cancel request" tone="danger" busy={busy}
        onConfirm={cancel} onCancel={() => setCancelId(null)}>
        <p className="small">Your pending request will be withdrawn. You can send a new one later.</p>
      </ConfirmDialog>
    </Panel>
  );
}
