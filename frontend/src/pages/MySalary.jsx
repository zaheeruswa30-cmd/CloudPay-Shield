import { Lock, Wallet } from "lucide-react";
import { fmtDate, fmtPKR, fmtPct } from "../api";
import { useApi } from "../context";
import { Empty, ErrorBox, Panel, SkeletonRows, StatusBadge } from "../components/ui";

export default function MySalary({ refreshKey }) {
  const salary = useApi("/salary/me", [refreshKey]);
  const requests = useApi("/salary-change-requests", [refreshKey]);

  return (
    <div className="page grid-2 align-start">
      <Panel title="My salary" icon={Wallet} subtitle="Only you (and authorised payroll staff) can see this record.">
        {salary.loading ? <SkeletonRows /> : salary.error ? (
          salary.error.status === 404 ? <Empty title="No payroll record linked">{salary.error.message} Ask a security administrator to link your account.</Empty> : <ErrorBox error={salary.error} onRetry={salary.reload} />
        ) : (
          <>
            <div className="salary-hero">
              <span className="muted small">{salary.data.full_name} · {salary.data.employee_code}</span>
              <div className="salary-amount mono">{fmtPKR(salary.data.current_salary)}<span className="muted small"> / month</span></div>
              <span className="muted small">{salary.data.job_title} · {salary.data.department} · version v{salary.data.salary_version}</span>
            </div>
            <h3 className="h3">Salary history</h3>
            {salary.data.history.length === 0 ? <Empty title="No recorded changes" /> : (
              <ul className="timeline">
                {salary.data.history.slice().reverse().map((h, i) => (
                  <li key={i}>
                    <span className="mono">{fmtPKR(h.old_salary)} → {fmtPKR(h.new_salary)}</span>
                    <span className={`mono ${h.pct_change >= 0 ? "up" : "down"}`}>{fmtPct(h.pct_change)}</span>
                    <span className="muted small">{fmtDate(h.effective_at)}{h.source === "seed_demo" ? " · demo data" : ""}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </Panel>
      <Panel title="Requests about my salary" icon={Lock} subtitle="Status only. Reviewer details and risk internals are restricted.">
        {requests.loading ? <SkeletonRows /> : requests.error ? <ErrorBox error={requests.error} /> : requests.data.length === 0 ? <Empty title="No requests" /> : (
          <ul className="timeline">
            {requests.data.map((r) => (
              <li key={r.id}>
                <span className="mono">{fmtPKR(r.current_salary)} → {fmtPKR(r.proposed_salary)}</span>
                <StatusBadge status={r.status} />
                <span className="muted small">{fmtDate(r.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
