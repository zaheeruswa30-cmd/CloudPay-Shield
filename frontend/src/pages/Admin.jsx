import { useEffect, useMemo, useState } from "react";
import {
  Ban, CheckCircle2, Inbox, KeyRound, Link2, Lock, Search, ShieldCheck, Unlock, UserCog, Users, XCircle,
} from "lucide-react";
import { api, fmtDate, fmtRelative, ROLE_LABEL } from "../api";
import { useApi, useAuth, useToast } from "../context";
import { ConfirmDialog, Empty, ErrorBox, Field, Panel, SkeletonRows, Stat } from "../components/ui";

const ROLE_ORDER = ["employee", "hr", "manager", "auditor", "admin"];

/** Each admin action: endpoint, minimum reason length, whether MFA step-up applies, and its extra fields. */
const ACTIONS = {
  role: { title: (u) => `Change role for ${u.username}`, path: (u) => `/admin/users/${u.id}/role`, min: 10, mfa: true, label: "Change role" },
  link: { title: (u) => `Link ${u.username} to a payroll record`, path: (u) => `/admin/users/${u.id}/link-employee`, min: 5, mfa: false, label: "Save link" },
  unlock: { title: (u) => `Unlock ${u.username}`, path: (u) => `/admin/users/${u.id}/unlock`, min: 5, mfa: true, label: "Unlock account" },
  mfa: { title: (u) => `Reset MFA for ${u.username}`, path: (u) => `/admin/users/${u.id}/reset-mfa`, min: 5, mfa: true, label: "Reset MFA", tone: "danger" },
  status: { title: (u) => `${u.is_active ? "Disable" : "Re-enable"} ${u.username}`, path: (u) => `/admin/users/${u.id}/status`, min: 5, mfa: true, label: "Confirm", tone: "danger" },
};

function useDebounced(v, ms = 300) {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

export default function Admin({ refreshKey, onRefresh }) {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const term = useDebounced(search.trim());
  const qs = new URLSearchParams();
  if (term) qs.set("search", term);
  if (role) qs.set("role", role);
  const users = useApi(`/admin/users${qs.toString() ? `?${qs}` : ""}`, [refreshKey]);
  const queue = useApi("/admin/access-requests?status=pending", [refreshKey]);
  const employees = useApi("/employees", [refreshKey]);
  const [action, setAction] = useState(null); // { kind, user } or { kind: "access", req, decision }
  const blocked = !user.mfa_enabled;
  const reload = () => { users.reload(); queue.reload(); onRefresh?.(); };
  const counts = users.data?.role_counts || {};

  return (
    <div className="page">
      {blocked && <div className="banner banner-warn"><KeyRound size={16} /> Admin actions are blocked until you enable MFA on the Account &amp; security page.</div>}
      {user.mfa_enabled && !user.mfa_verified_session && (
        <div className="banner banner-info small"><KeyRound size={15} /> This session was not MFA-verified. Each sensitive action will ask for a current authenticator code.</div>
      )}

      <div className="stats">
        {ROLE_ORDER.map((r) => <Stat key={r} label={ROLE_LABEL[r]} value={counts[r] ?? "…"} icon={r === "admin" ? ShieldCheck : Users} tone={r === "admin" ? "warn" : undefined} />)}
      </div>

      <Panel title="Pending access requests" icon={Inbox} subtitle="Users asking for a privileged role. Approving changes their role immediately.">
        {queue.error ? <ErrorBox error={queue.error} onRetry={queue.reload} /> : queue.loading && !queue.data ? <SkeletonRows /> :
          (queue.data || []).length === 0 ? <Empty title="No pending access requests" /> : (
            <ul className="access-queue">
              {queue.data.map((a) => (
                <li key={a.id} className="access-item">
                  <div>
                    <strong>{a.full_name}</strong> <span className="mono small muted">{a.username}</span>
                    <div className="small">{ROLE_LABEL[a.current_role]} → <strong>{a.requested_role_label}</strong> · {fmtRelative(a.created_at)}</div>
                    <p className="small muted">“{a.justification}”</p>
                  </div>
                  <div className="btn-row">
                    <button className="btn btn-ok btn-sm" disabled={blocked} onClick={() => setAction({ kind: "access", req: a, decision: "approve" })}><CheckCircle2 size={14} /> Approve</button>
                    <button className="btn btn-crit btn-sm" disabled={blocked} onClick={() => setAction({ kind: "access", req: a, decision: "reject" })}><XCircle size={14} /> Reject</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
      </Panel>

      <Panel title="Users & access" icon={UserCog} subtitle="Roles are assigned here, never through public sign-up. Every change needs a reason and is audited.">
        <div className="filters">
          <label className="search-box"><Search size={15} aria-hidden />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search username, name or email" aria-label="Search users" />
          </label>
          <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role filter">
            <option value="">All roles</option>{ROLE_ORDER.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
        </div>
        {users.error ? <ErrorBox error={users.error} onRetry={users.reload} /> : users.loading && !users.data ? <SkeletonRows rows={6} /> :
          users.data.users.length === 0 ? <Empty title="No users match" /> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>User</th><th>Role</th><th>MFA</th><th>Status</th><th className="hide-sm">Payroll record</th><th className="hide-sm">Created</th><th>Actions</th></tr></thead>
                <tbody>
                  {users.data.users.map((u) => {
                    const self = u.id === user.id;
                    return (
                      <tr key={u.id}>
                        <td><span className="cell-main">{u.full_name}</span><div className="mono tiny muted">{u.username}{self ? " (you)" : ""}</div></td>
                        <td><span className={`role-pill role-${u.role}`}>{u.role_label}</span></td>
                        <td>{u.mfa_enabled ? <span className="integ ok">On</span> : <span className="integ muted">Off</span>}</td>
                        <td>{!u.is_active ? <span className="integ crit">Disabled</span> : u.locked ? <span className="integ warn">Locked</span> : <span className="integ ok">Active</span>}</td>
                        <td className="small hide-sm">{u.employee_code ? <><span className="mono">{u.employee_code}</span> <span className="muted">{u.employee_name}</span></> : <span className="muted">—</span>}</td>
                        <td className="small muted hide-sm">{fmtDate(u.created_at)}</td>
                        <td>
                          <div className="icon-actions">
                            <button className="icon-btn" title="Change role" aria-label={`Change role for ${u.username}`} disabled={blocked || self} onClick={() => setAction({ kind: "role", user: u })}><UserCog size={16} /></button>
                            <button className="icon-btn" title="Link payroll record" aria-label={`Link payroll record for ${u.username}`} disabled={blocked} onClick={() => setAction({ kind: "link", user: u })}><Link2 size={16} /></button>
                            <button className="icon-btn" title="Unlock sign-in" aria-label={`Unlock ${u.username}`} disabled={blocked || !u.locked} onClick={() => setAction({ kind: "unlock", user: u })}><Unlock size={16} /></button>
                            <button className="icon-btn" title="Reset MFA" aria-label={`Reset MFA for ${u.username}`} disabled={blocked || self || !u.mfa_enabled} onClick={() => setAction({ kind: "mfa", user: u })}><KeyRound size={16} /></button>
                            <button className="icon-btn" title={u.is_active ? "Disable account" : "Re-enable account"} aria-label={`${u.is_active ? "Disable" : "Enable"} ${u.username}`} disabled={blocked || self} onClick={() => setAction({ kind: "status", user: u })}>{u.is_active ? <Ban size={16} /> : <Lock size={16} />}</button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        <p className="tiny muted">Safeguards enforced by the API: no changes to your own role, MFA or status; the last active administrator cannot be removed; manager and admin roles keep MFA mandatory.</p>
      </Panel>

      {action && <ActionDialog action={action} employees={employees.data || []} onClose={() => setAction(null)} onDone={() => { setAction(null); reload(); }} />}
    </div>
  );
}

function ActionDialog({ action, employees, onClose, onDone }) {
  const { user } = useAuth();
  const toast = useToast();
  const isAccess = action.kind === "access";
  const cfg = isAccess
    ? { min: 10, mfa: true, label: action.decision === "approve" ? "Approve and grant role" : "Reject request", tone: action.decision === "approve" ? "ok" : "danger" }
    : ACTIONS[action.kind];
  const u = action.user;
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const [newRole, setNewRole] = useState(u?.role || "employee");
  const [employeeId, setEmployeeId] = useState(u?.employee_id ? String(u.employee_id) : "");
  const [busy, setBusy] = useState(false);
  const needCode = cfg.mfa && !user.mfa_verified_session;
  const valid = reason.trim().length >= cfg.min && (!needCode || code.length >= 6) && (action.kind !== "role" || newRole !== u.role);
  const unlinked = useMemo(() => employees, [employees]);

  async function run() {
    setBusy(true);
    const body = { reason: reason.trim() };
    if (needCode) body.mfa_code = code;
    let path;
    if (isAccess) { path = `/admin/access-requests/${action.req.id}/decision`; body.decision = action.decision; }
    else {
      path = cfg.path(u);
      if (action.kind === "role") body.role = newRole;
      if (action.kind === "link") { body.employee_id = employeeId ? Number(employeeId) : null; delete body.mfa_code; }
      if (action.kind === "status") body.is_active = !u.is_active;
    }
    try {
      await api(path, { method: "POST", body });
      toast.success(isAccess ? `Access request ${action.decision === "approve" ? "approved" : "rejected"}.` : "Change saved and audited.");
      onDone();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  const title = isAccess ? `${action.decision === "approve" ? "Approve" : "Reject"} ${action.req.username}'s request for ${action.req.requested_role_label}` : cfg.title(u);
  return (
    <ConfirmDialog open title={title} confirmLabel={cfg.label} tone={cfg.tone} busy={busy} disabled={!valid} onConfirm={run} onCancel={onClose}>
      <div className="form">
        {isAccess && <p className="small muted">“{action.req.justification}”</p>}
        {action.kind === "role" && (
          <Field label="New role">
            <select value={newRole} onChange={(e) => setNewRole(e.target.value)}>
              {ROLE_ORDER.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
          </Field>
        )}
        {action.kind === "role" && ["manager", "admin"].includes(newRole) && <p className="tiny warn-text">This role must enrol in MFA before it can approve or administer.</p>}
        {action.kind === "link" && (
          <Field label="Payroll record" hint="Lets an employee account see its own salary on the My salary page.">
            <select value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
              <option value="">No link</option>
              {unlinked.map((e) => <option key={e.id} value={e.id}>{e.employee_code} — {e.full_name}</option>)}
            </select>
          </Field>
        )}
        {action.kind === "mfa" && <p className="small">The user's authenticator and recovery codes stop working. They must enrol again at next sign-in.</p>}
        {action.kind === "status" && <p className="small">{u.is_active ? "The user is signed out and cannot sign in until re-enabled." : "The user can sign in again."}</p>}
        <Field label={`Reason (required, ${cfg.min}+ characters)`} hint="Recorded in the audit trail and shown to the user.">
          <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
        </Field>
        {needCode && (
          <Field label="Your authenticator code" hint="Required because this session was not MFA-verified.">
            <input className="mono" inputMode="numeric" autoComplete="one-time-code" maxLength={12} value={code} onChange={(e) => setCode(e.target.value.trim())} />
          </Field>
        )}
      </div>
    </ConfirmDialog>
  );
}
