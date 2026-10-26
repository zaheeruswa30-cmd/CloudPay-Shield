import { useEffect, useState } from "react";
import { CheckCircle2, GitCompareArrows, History, KeyRound, ShieldAlert, XCircle } from "lucide-react";
import { api, fmtDate, fmtPKR, fmtPct } from "../api";
import { useAuth, useToast } from "../context";
import { ConfirmDialog, Drawer, ErrorBox, Field, Loading, RiskBadge, StatusBadge } from "./ui";
import { RiskBreakdown } from "./risk";

export default function RequestDrawer({ requestId, onClose, onChanged }) {
  const { user } = useAuth();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [reason, setReason] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(null); // "approve" | "reject"
  const [history, setHistory] = useState(null);

  const load = () => {
    setError(null);
    api(`/salary-change-requests/${requestId}`).then((d) => {
      setData(d);
      if (user?.role !== "employee") {
        api(`/salary-change-requests?employee_id=${d.employee_id}`).then((rows) => setHistory(rows.filter((r) => r.id !== d.id))).catch(() => setHistory([]));
      }
    }).catch(setError);
  };
  useEffect(() => {
    if (requestId) {
      setData(null);
      setHistory(null);
      setConfirm(null);
      setReason("");
      setMfaCode("");
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestId]);

  const isManager = user?.role === "manager";
  const canDecide = isManager && data?.status === "pending";
  const ownRequest = data && data.requested_by_id === user?.id;
  const highRisk = data && ["High", "Critical"].includes(data.risk_level);
  const minReason = highRisk ? 20 : 10;
  const needsStepUp = isManager && user?.mfa_enabled && !user?.mfa_verified_session;

  async function decide(decision) {
    setBusy(true);
    try {
      const body = { decision, reason };
      if (needsStepUp) body.mfa_code = mfaCode;
      const updated = await api(`/salary-change-requests/${requestId}/decision`, { method: "POST", body });
      toast.success(`Request #${requestId} ${updated.status}.${updated.status === "approved" ? " Salary updated and audited." : ""}`);
      setConfirm(null);
      setReason("");
      setMfaCode("");
      onChanged?.();
      load();
    } catch (e) {
      setConfirm(null);
      toast.error(e.message);
      if (e.status === 409) load();
    } finally {
      setBusy(false);
    }
  }

  const live = data?.live_assessment;
  return (
    <Drawer open={!!requestId} onClose={onClose} title={`Salary change request #${requestId ?? ""}`}>
      <ErrorBox error={error} onRetry={load} />
      {!data && !error && <Loading />}
      {data && (
        <>
          <div className="detail-grid">
            <div><span className="muted small">Employee</span><strong>{data.employee_name}</strong><span className="mono small muted">{data.employee_code} · {data.department}</span></div>
            <div><span className="muted small">Status</span><StatusBadge status={data.status} /></div>
            <div><span className="muted small">Current → proposed</span><strong className="mono">{fmtPKR(data.current_salary)} → {fmtPKR(data.proposed_salary)}</strong><span className={`mono small ${data.pct_change > 0 ? "up" : "down"}`}>{fmtPct(data.pct_change)}</span></div>
            <div><span className="muted small">Submitted</span><span>{data.requested_by ?? "—"} · {fmtDate(data.created_at)}</span><span className="muted small">Source: {data.source}</span></div>
          </div>
          <div className="reason-box"><span className="muted small">Reason given</span><p>{data.reason || <em className="muted">(none)</em>}</p></div>

          {data.is_stale && (
            <div className="banner banner-warn" role="alert">
              <GitCompareArrows size={16} /> Version conflict: prepared against salary v{data.base_salary_version}, current is v{data.current_salary_version}. It cannot be approved; reject it and ask HR to resubmit.
            </div>
          )}

          {data.status !== "pending" && (
            <div className={`banner ${data.status === "approved" ? "banner-ok" : "banner-crit"}`}>
              {data.status === "approved" ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
              {data.status === "approved" ? "Approved" : "Rejected"} by {data.decided_by} on {fmtDate(data.decided_at)} — “{data.decision_reason}”
            </div>
          )}

          {highRisk && data.status === "pending" && (
            <div className="banner banner-info small"><ShieldAlert size={15} /> Flagged for enhanced review. This is a rule-based risk score, not a finding of fraud. Verify the supporting evidence before deciding.</div>
          )}
          <h3 className="h3">Risk assessment at submission</h3>
          <RiskBreakdown assessment={data.risk_assessment} />

          {live && live.score !== data.risk_score && (
            <>
              <h3 className="h3">Live re-check (current state)</h3>
              <p className="muted small">Score now {live.score} ({live.level}) — conditions changed since submission.</p>
              <ul className="small">{live.explanations.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </>
          )}

          <h3 className="h3"><History size={15} /> Other requests for this employee</h3>
          {history === null ? <Loading /> : history.length === 0 ? <p className="small muted">No other requests for this employee.</p> : (
            <ul className="req-mini">
              {history.slice(0, 8).map((r) => (
                <li key={r.id}><a href={`#/requests/${r.id}`}>
                  <span className="mono">#{r.id}</span><StatusBadge status={r.status} /><RiskBadge level={r.risk_level} score={r.risk_score} />
                  <span className="mono">{fmtPct(r.pct_change)}</span><span className="small muted">{fmtDate(r.created_at)}</span>
                </a></li>
              ))}
            </ul>
          )}

          {canDecide && (
            <div className="decision">
              <h3 className="h3">Manager decision</h3>
              {ownRequest && <div className="banner banner-crit">You submitted this request. Separation of duties blocks your decision.</div>}
              {!user.mfa_enabled && (
                <div className="banner banner-warn"><KeyRound size={16} /> MFA is required for decisions. Enable it in Security settings first.</div>
              )}
              <Field label={`Decision reason (required, ${minReason}+ characters)`} hint={highRisk ? "High/Critical risk: document what you verified." : "Recorded in the audit trail."}>
                <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} placeholder="e.g. Verified promotion letter #PR-2026-114 with department head." />
              </Field>
              {needsStepUp && (
                <Field label="Authenticator code" hint="Your session was not MFA-verified; enter a current 6-digit code.">
                  <input inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\s/g, ""))} />
                </Field>
              )}
              <div className="btn-row">
                <button className="btn btn-ok" disabled={busy || reason.trim().length < minReason || data.is_stale} onClick={() => setConfirm("approve")}>
                  <CheckCircle2 size={16} /> Approve &amp; apply
                </button>
                <button className="btn btn-crit" disabled={busy || reason.trim().length < minReason} onClick={() => setConfirm("reject")}>
                  <XCircle size={16} /> Reject
                </button>
              </div>
            </div>
          )}
          <ConfirmDialog open={!!confirm} busy={busy} tone={confirm === "approve" ? "ok" : "danger"}
            title={confirm === "approve" ? `Approve request #${data.id}?` : `Reject request #${data.id}?`}
            confirmLabel={confirm === "approve" ? "Approve and apply salary" : "Reject request"}
            disabled={needsStepUp && mfaCode.length < 6}
            onConfirm={() => decide(confirm)} onCancel={() => setConfirm(null)}>
            <div className="stack">
              <p className="small">{data.employee_name}: <span className="mono">{fmtPKR(data.current_salary)} → {fmtPKR(data.proposed_salary)}</span> ({fmtPct(data.pct_change)}) · <RiskBadge level={data.risk_level} score={data.risk_score} /></p>
              <div className="reason-box"><span className="muted small">Your reason</span><p>{reason}</p></div>
              <p className="small muted">{confirm === "approve"
                ? "The backend re-checks the salary version, separation of duties and MFA, then updates the salary and writes an audit event."
                : "The salary will not change. The submitter is notified and the decision is audited."}</p>
              {needsStepUp && <p className="small warn-text">Enter your authenticator code in the form before confirming.</p>}
            </div>
          </ConfirmDialog>
        </>
      )}
    </Drawer>
  );
}
