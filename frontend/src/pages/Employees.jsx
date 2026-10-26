import { useEffect, useMemo, useState } from "react";
import { Building2, ChevronRight, History, Lock, Search, Users } from "lucide-react";
import { fmtDate, fmtPct, fmtPKR } from "../api";
import { useApi, useAuth } from "../context";
import { Drawer, Empty, ErrorBox, Panel, RiskBadge, SkeletonRows, StatusBadge } from "../components/ui";

function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

const Salary = ({ value, visible }) =>
  visible ? <span className="mono">{fmtPKR(value)}</span> : <span className="restricted"><Lock size={12} /> Restricted</span>;

export default function Employees({ refreshKey, param, go }) {
  const { user } = useAuth();
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("");
  const term = useDebounced(q.trim());
  const params = new URLSearchParams();
  if (term) params.set("search", term);
  if (dept) params.set("department", dept);
  const qs = params.toString();
  const all = useApi("/employees", [refreshKey]); // unfiltered list, used for department options and totals
  const list = useApi(qs ? `/employees?${qs}` : "/employees", [refreshKey]);
  const departments = useMemo(() => [...new Set((all.data || []).map((e) => e.department))].sort(), [all.data]);
  const rows = list.data || [];
  const anySeed = rows.some((e) => e.is_demo_seed);
  const salaryVisible = rows[0]?.salary_visible ?? ["hr", "manager"].includes(user.role);
  const openId = param ? Number(param) : null;

  return (
    <div className="page">
      {!salaryVisible && (
        <div className="banner banner-info"><Lock size={15} /> Salary amounts are hidden for the {user.role} role. Only HR and payroll managers can see pay figures (enforced by the API).</div>
      )}
      <Panel title="Employee directory" icon={Users}
        subtitle={`${rows.length} of ${all.data?.length ?? "…"} employees${anySeed ? " · fictional seeded demo records" : ""}`}>
        <div className="filters">
          <label className="search-box"><Search size={15} aria-hidden />
            <input placeholder="Search name, employee code or job title" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search employees" />
          </label>
          <select value={dept} onChange={(e) => setDept(e.target.value)} aria-label="Department filter">
            <option value="">All departments</option>
            {departments.map((d) => <option key={d}>{d}</option>)}
          </select>
          {(q || dept) && <button className="btn btn-ghost btn-sm" onClick={() => { setQ(""); setDept(""); }}>Clear</button>}
        </div>
        {list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : list.loading && !list.data ? <SkeletonRows rows={6} /> :
          rows.length === 0 ? <Empty title="No employees match">Try a different search or department.</Empty> : (
            <div className="table-wrap">
              <table className="table table-click">
                <thead><tr><th>Code</th><th>Name</th><th>Department</th><th className="hide-sm">Title</th><th className="num">Salary</th><th className="num hide-sm">Version</th><th className="hide-sm">Updated</th><th aria-label="Open" /></tr></thead>
                <tbody>
                  {rows.map((e) => (
                    <tr key={e.id} onClick={() => go("employees", e.id)} tabIndex={0} onKeyDown={(ev) => ev.key === "Enter" && go("employees", e.id)}>
                      <td className="mono">{e.employee_code}</td>
                      <td className="cell-main">{e.full_name}</td>
                      <td>{e.department}</td>
                      <td className="muted hide-sm">{e.job_title}</td>
                      <td className="num"><Salary value={e.current_salary} visible={e.salary_visible} /></td>
                      <td className="num mono hide-sm">v{e.salary_version}</td>
                      <td className="small muted hide-sm">{fmtDate(e.updated_at)}</td>
                      <td><ChevronRight size={16} className="muted" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Panel>
      <EmployeeDrawer id={openId} onClose={() => go("employees")} go={go} refreshKey={refreshKey} />
    </div>
  );
}

function EmployeeDrawer({ id, onClose, go, refreshKey }) {
  const { user } = useAuth();
  const { data: e, loading, error, reload } = useApi(id ? `/employees/${id}` : null, [refreshKey]);
  const canRequest = user.role === "hr";
  const canOpenRequest = ["hr", "manager", "auditor"].includes(user.role);
  return (
    <Drawer open={!!id} onClose={onClose} title={e ? e.full_name : "Employee details"}>
      {error ? <ErrorBox error={error} onRetry={reload} /> : loading || !e ? <SkeletonRows rows={5} /> : (
        <div className="stack">
          <dl className="kv">
            <div><dt>Employee code</dt><dd className="mono">{e.employee_code}</dd></div>
            <div><dt>Department</dt><dd><Building2 size={13} /> {e.department}</dd></div>
            <div><dt>Job title</dt><dd>{e.job_title}</dd></div>
            <div><dt>Current salary</dt><dd><Salary value={e.current_salary} visible={e.salary_visible} /></dd></div>
            <div><dt>Salary version</dt><dd className="mono">v{e.salary_version}</dd></div>
            <div><dt>Linked account</dt><dd>{e.linked_username ? <span className="mono">{e.linked_username}</span> : e.has_linked_account ? "Yes" : "None"}</dd></div>
          </dl>
          {e.is_demo_seed && <p className="tiny muted">Fictional seeded demonstration record.</p>}
          {e.open_requests > 0 && <div className="banner banner-warn">{e.open_requests} pending salary request{e.open_requests > 1 ? "s" : ""} for this employee.</div>}
          {canRequest && <button className="btn btn-primary" onClick={() => go("new-request", null, { employee: e.id })}>New salary change request</button>}

          <section>
            <h3 className="section-title"><History size={15} /> Salary history</h3>
            {e.history.length === 0 ? <p className="small muted">No applied salary changes.</p> : (
              <div className="table-wrap">
                <table className="table compact">
                  <thead><tr><th>Effective</th><th className="num">Old</th><th className="num">New</th><th className="num">Change</th><th>Source</th></tr></thead>
                  <tbody>
                    {e.history.map((h, i) => (
                      <tr key={i}>
                        <td className="small">{fmtDate(h.effective_at)}</td>
                        <td className="num"><Salary value={h.old_salary} visible={e.salary_visible} /></td>
                        <td className="num"><Salary value={h.new_salary} visible={e.salary_visible} /></td>
                        <td className="num mono">{fmtPct(h.pct_change)}</td>
                        <td className="small muted">{h.source === "seed_demo" ? "Seeded demo" : h.request_id ? `Request #${h.request_id}` : h.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section>
            <h3 className="section-title">Salary change requests</h3>
            {e.requests.length === 0 ? <p className="small muted">No requests for this employee.</p> : (
              <ul className="req-mini">
                {e.requests.map((r) => (
                  <li key={r.id}>
                    <button disabled={!canOpenRequest} onClick={() => go("requests", r.id)}>
                      <span className="mono">#{r.id}</span>
                      <StatusBadge status={r.status} />
                      <RiskBadge level={r.risk_level} score={r.risk_score} />
                      <span className="mono">{fmtPct(r.pct_change)}</span>
                      <span className="small muted">{fmtDate(r.created_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </Drawer>
  );
}
