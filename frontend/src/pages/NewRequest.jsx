import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, FilePlus2, History, Send, ShieldQuestion } from "lucide-react";
import { api, fmtDate, fmtPKR, fmtPct, pctChange } from "../api";
import { useApi, useToast } from "../context";
import { ConfirmDialog, Empty, ErrorBox, Field, Panel, RiskBadge, SkeletonRows, StatusBadge } from "../components/ui";
import { RiskBreakdown } from "../components/risk";

const MIN_REASON = 5;

export default function NewRequest({ refreshKey, onRefresh, go, query }) {
  const toast = useToast();
  const employees = useApi("/employees", [refreshKey]);
  const mine = useApi("/salary-change-requests?mine=true", [refreshKey]);
  const [employeeId, setEmployeeId] = useState(query?.employee || "");
  const [proposed, setProposed] = useState("");
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const emp = useMemo(() => (employees.data || []).find((e) => String(e.id) === String(employeeId)), [employees.data, employeeId]);
  const proposedNum = Number(String(proposed).replace(/[,\s]/g, ""));
  const validAmount = proposed !== "" && Number.isInteger(proposedNum) && proposedNum > 0;
  const pct = emp && validAmount ? pctChange(emp.current_salary, proposedNum) : null;
  const sameAsCurrent = emp && validAmount && proposedNum === emp.current_salary;
  const reasonOk = reason.trim().length >= MIN_REASON;
  const errors = {
    employee: !emp ? "Select an employee." : "",
    amount: !validAmount ? "Enter a positive whole number of rupees." : sameAsCurrent ? "The proposed salary equals the current salary." : "",
    reason: !reasonOk ? `A business reason of at least ${MIN_REASON} characters is required.` : "",
  };
  const formValid = !errors.employee && !errors.amount && !errors.reason;
  const duplicates = preview?.open_requests || [];

  // Live risk preview from the backend (nothing is saved).
  useEffect(() => {
    if (!emp || !validAmount || sameAsCurrent) { setPreview(null); return; }
    const t = setTimeout(() => {
      api("/risk/assess", { method: "POST", body: { employee_id: emp.id, proposed_salary: proposedNum, reason } })
        .then((p) => { setPreview(p); setPreviewError(null); })
        .catch(setPreviewError);
    }, 400);
    return () => clearTimeout(t);
  }, [emp, proposedNum, reason, validAmount, sameAsCurrent]);

  function review(e) {
    e.preventDefault();
    setTouched(true);
    if (formValid) setConfirming(true);
  }

  async function submit() {
    setBusy(true);
    try {
      const r = await api("/salary-change-requests", {
        method: "POST",
        body: { employee_id: emp.id, proposed_salary: proposedNum, reason: reason.trim(), expected_salary_version: emp.salary_version },
      });
      setResult(r);
      setConfirming(false);
      toast.success(`Request #${r.id} submitted. Awaiting manager review.`);
      setProposed(""); setReason(""); setPreview(null); setTouched(false);
      mine.reload();
      onRefresh?.();
    } catch (err) {
      toast.error(err.message);
      setConfirming(false);
      if (err.status === 409) employees.reload();
    } finally {
      setBusy(false);
    }
  }

  if (employees.error) return <ErrorBox error={employees.error} onRetry={employees.reload} />;

  return (
    <div className="page">
      {result && (
        <div className="confirm-panel">
          <CheckCircle2 size={26} className="ok-text" />
          <div>
            <strong>Request #{result.id} submitted for {result.employee_name}</strong>
            <p className="small muted">
              Status: <StatusBadge status={result.status} /> · Risk: <RiskBadge level={result.risk_level} score={result.risk_score} />.
              The salary stays at {fmtPKR(result.current_salary)} until a payroll manager approves this request.
              {result.manual_review_required && " This request needs enhanced review because of its risk level."}
            </p>
          </div>
          <div className="row-actions">
            <button className="btn btn-ghost btn-sm" onClick={() => go("requests", result.id)}>Open request</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setResult(null)}>New request</button>
          </div>
        </div>
      )}

      <div className="grid-2 align-start">
        <Panel title="New salary change request" icon={FilePlus2} subtitle="Submitting does not change the salary. A payroll manager must approve first.">
          {employees.loading ? <SkeletonRows /> : (
            <form className="form" onSubmit={review} noValidate>
              <Field label="Employee" error={touched && errors.employee}>
                <select value={employeeId} onChange={(e) => { setEmployeeId(e.target.value); setResult(null); }}>
                  <option value="">Select an employee…</option>
                  {employees.data.map((e) => <option key={e.id} value={e.id}>{e.full_name} — {e.employee_code} ({e.department})</option>)}
                </select>
              </Field>
              {emp && (
                <div className="emp-card">
                  <div><span className="muted small">Current salary</span><strong className="mono">{fmtPKR(emp.current_salary)}</strong></div>
                  <div><span className="muted small">Salary version</span><strong className="mono">v{emp.salary_version}</strong></div>
                  <div><span className="muted small">Title</span><span>{emp.job_title}</span></div>
                </div>
              )}
              <Field label="Proposed monthly salary (PKR)" error={(touched || proposed) && errors.amount}
                hint="Whole rupees, e.g. 275000">
                <input inputMode="numeric" value={proposed} onChange={(e) => setProposed(e.target.value)} placeholder="275000" />
              </Field>
              <div className={`pct-readout ${pct === null ? "" : pct >= 0 ? "up" : "down"}`} aria-live="polite">
                <span className="small muted">Percentage change</span>
                <strong className="mono">{pct === null ? "—" : fmtPct(pct)}</strong>
                <span className="tiny muted">((proposed − current) ÷ current) × 100</span>
              </div>
              {duplicates.length > 0 && (
                <div className="banner banner-warn" role="alert">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>Possible duplicate:</strong> {emp.full_name} already has {duplicates.length} pending request{duplicates.length > 1 ? "s" : ""}:
                    <ul className="dup-list">
                      {duplicates.map((d) => (
                        <li key={d.id}><a href={`#/requests/${d.id}`}>#{d.id}</a> · {fmtPKR(d.proposed_salary)} ({fmtPct(d.pct_change)}) · {d.risk_level} · by {d.requested_by} · {fmtDate(d.created_at)}</li>
                      ))}
                    </ul>
                    Submitting another will add risk points and both will go to review.
                  </div>
                </div>
              )}
              <Field label="Business reason (required)" error={(touched || reason) && errors.reason}
                hint="Explain why: promotion, review outcome, policy reference. Vague reasons raise the risk score.">
                <textarea rows={4} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} />
              </Field>
              <span className="tiny muted right">{reason.trim().length}/1000</span>
              <button className="btn btn-primary" disabled={busy}><Send size={16} /> Review and submit</button>
            </form>
          )}
        </Panel>

        <Panel title="Risk assessment preview" icon={ShieldQuestion} subtitle="Calculated by the backend as you type. Nothing is saved.">
          {previewError ? <ErrorBox error={previewError} /> :
            preview ? <RiskBreakdown assessment={preview} /> :
              <Empty title="Select an employee and enter an amount">The explainable risk assessment will appear here.</Empty>}
          <p className="tiny muted">A high score means the request needs closer review. It is not a finding of fraud.</p>
        </Panel>
      </div>

      <Panel title="My recent submissions" icon={History} subtitle="Requests you submitted and their current status">
        {mine.error ? <ErrorBox error={mine.error} onRetry={mine.reload} /> : mine.loading && !mine.data ? <SkeletonRows /> :
          (mine.data || []).length === 0 ? <Empty title="You haven't submitted any requests yet" /> : (
            <div className="table-wrap">
              <table className="table table-click">
                <thead><tr><th>#</th><th>Employee</th><th className="num">Proposed</th><th className="num">Change</th><th>Risk</th><th>Status</th><th className="hide-sm">Submitted</th></tr></thead>
                <tbody>
                  {mine.data.slice(0, 10).map((r) => (
                    <tr key={r.id} onClick={() => go("requests", r.id)}>
                      <td className="mono">#{r.id}</td>
                      <td className="cell-main">{r.employee_name}</td>
                      <td className="num mono">{fmtPKR(r.proposed_salary)}</td>
                      <td className="num mono">{fmtPct(r.pct_change)}</td>
                      <td><RiskBadge level={r.risk_level} score={r.risk_score} /></td>
                      <td><StatusBadge status={r.status} /></td>
                      <td className="small muted hide-sm"><Clock size={12} /> {fmtDate(r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Panel>

      <ConfirmDialog open={confirming} title="Submit salary change request?" confirmLabel="Submit for approval" busy={busy}
        onConfirm={submit} onCancel={() => setConfirming(false)}>
        {emp && (
          <div className="stack">
            <dl className="kv">
              <div><dt>Employee</dt><dd>{emp.full_name} ({emp.employee_code})</dd></div>
              <div><dt>Current</dt><dd className="mono">{fmtPKR(emp.current_salary)}</dd></div>
              <div><dt>Proposed</dt><dd className="mono">{fmtPKR(proposedNum)}</dd></div>
              <div><dt>Change</dt><dd className="mono">{fmtPct(pct)}</dd></div>
              {preview && <div><dt>Risk</dt><dd><RiskBadge level={preview.level} score={preview.score} /></dd></div>}
            </dl>
            {duplicates.length > 0 && <div className="banner banner-warn small">This employee already has {duplicates.length} pending request(s).</div>}
            <p className="small muted">The request goes to a payroll manager. The salary will not change unless they approve it.</p>
          </div>
        )}
      </ConfirmDialog>
    </div>
  );
}
