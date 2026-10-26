import { useMemo, useState } from "react";
import {
  Activity, AlertTriangle, CheckCircle2, Clock, FileWarning, Search, ShieldAlert, Siren, TrendingUp, Users, XCircle,
} from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { fmtDate, fmtPct, fmtRelative } from "../api";
import { useApi, useAuth } from "../context";
import { Empty, ErrorBox, Panel, RISK_COLORS, RiskBadge, SkeletonRows, Stat } from "../components/ui";
import { RiskGauge } from "../components/risk";
import RequestTable from "../components/RequestTable";
import RequestDrawer from "../components/RequestDrawer";

const tooltipStyle = {
  contentStyle: { background: "#0f1a2b", border: "1px solid #1f3350", borderRadius: 8, color: "#e2ecf7" },
  labelStyle: { color: "#8aa4c2" },
};

export default function Overview({ refreshKey, onRefresh, go }) {
  const { user } = useAuth();
  const canAudit = ["auditor", "manager"].includes(user.role);
  const summary = useApi("/analytics/summary", [refreshKey]);
  const requests = useApi("/salary-change-requests", [refreshKey]);
  const audit = useApi(canAudit ? "/audit-events?limit=8" : null, [refreshKey]);
  const [openId, setOpenId] = useState(null);

  const s = summary.data;
  const [q, setQ] = useState("");
  const [statusF, setStatusF] = useState("all");
  const [riskF, setRiskF] = useState("all");
  const recent = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (requests.data || []).filter((r) =>
      (statusF === "all" || r.status === statusF) &&
      (riskF === "all" || r.risk_level === riskF) &&
      (!term || [r.employee_name, r.employee_code, r.department, String(r.id)].some((v) => (v || "").toLowerCase().includes(term)))
    ).slice(0, 8);
  }, [requests.data, q, statusF, riskF]);
  const activity = useMemo(() => (s?.request_activity || []).map((d) => ({
    ...d, label: new Date(`${d.date}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  })), [s]);
  const activityTotal = activity.reduce((n, d) => n + d.submitted + d.approved + d.rejected, 0);
  const statusData = useMemo(
    () => (s ? [
      { name: "Pending", value: s.status_counts.pending, color: "#f5b301" },
      { name: "Approved", value: s.status_counts.approved, color: "#22c55e" },
      { name: "Rejected", value: s.status_counts.rejected, color: "#f43f5e" },
    ] : []),
    [s]
  );
  const statusSlices = statusData.filter((d) => d.value > 0);
  const riskData = useMemo(
    () => (s ? Object.entries(s.risk_counts).map(([level, count]) => ({ level, count })) : []),
    [s]
  );
  const trend = useMemo(
    () => (s ? s.salary_change_history.map((h, i) => ({ ...h, t: new Date(h.date).getTime(), i })) : []),
    [s]
  );
  const alerts = useMemo(
    () => (requests.data || []).filter((r) => r.status === "pending" && ["High", "Critical"].includes(r.risk_level)).slice(0, 5),
    [requests.data]
  );
  const seededOnly = s && s.history_sources && Object.keys(s.history_sources).length > 0 &&
    Object.keys(s.history_sources).every((k) => k === "seed_demo");

  if (summary.error) return <ErrorBox error={summary.error} onRetry={summary.reload} />;

  return (
    <div className="page">
      <div className="stats">
        {!s ? <SkeletonRows rows={1} /> : (
          <>
            <Stat label="Employees" value={s.total_employees} icon={Users} />
            <Stat label="Pending requests" value={s.status_counts.pending} icon={Clock} tone="warn" hint={`${s.stale_pending} with version conflicts`} />
            <Stat label="High-risk pending" value={s.pending_high_risk} icon={AlertTriangle} tone="high" />
            <Stat label="Critical alerts" value={s.pending_critical} icon={Siren} tone="crit" />
            <Stat label="Approved" value={s.status_counts.approved} icon={CheckCircle2} tone="ok" />
            <Stat label="Rejected" value={s.status_counts.rejected} icon={XCircle} tone="muted" />
            <Stat label="Audit events (24h)" value={s.audit_events_24h} icon={Activity} hint={`${s.security_events_24h} denied / failed`} />
          </>
        )}
      </div>

      <div className="grid-3">
        <Panel title="Risk overview" icon={ShieldAlert} subtitle="Highest score among pending requests">
          {s ? <RiskGauge score={s.pending_max_risk} caption={`Average pending score ${s.pending_avg_risk}`} /> : <SkeletonRows />}
        </Panel>
        <Panel title="Request status" icon={Clock}>
          {!s ? <SkeletonRows /> : s.total_requests === 0 ? <Empty title="No requests yet" /> : (
            <div className="chart-sm">
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={statusSlices} dataKey="value" nameKey="name" innerRadius={52} outerRadius={80} paddingAngle={statusSlices.length > 1 ? 3 : 0} stroke="none">
                    {statusSlices.map((d) => <Cell key={d.name} fill={d.color} />)}
                  </Pie>
                  <Tooltip {...tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
              <ul className="legend inline">
                {statusData.map((d) => <li key={d.name}><span className="swatch" style={{ background: d.color }} />{d.name} <span className="mono">{d.value}</span></li>)}
              </ul>
            </div>
          )}
        </Panel>
        <Panel title="Risk distribution" icon={FileWarning} subtitle="All requests by risk level">
          {!s ? <SkeletonRows /> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={riskData} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="#1a2a42" vertical={false} />
                <XAxis dataKey="level" stroke="#6f87a6" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis allowDecimals={false} stroke="#6f87a6" tickLine={false} axisLine={false} fontSize={12} />
                <Tooltip {...tooltipStyle} cursor={{ fill: "rgba(34,211,238,0.06)" }} />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                  {riskData.map((d) => <Cell key={d.level} fill={RISK_COLORS[d.level]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>
      </div>

      <Panel title="Request activity" icon={TrendingUp} subtitle="Last 14 days · submitted requests and manager decisions">
        {!s ? <SkeletonRows /> : activityTotal === 0 ? <Empty title="No request activity in the last 14 days" /> : (
          <ResponsiveContainer width="100%" height={230}>
            <AreaChart data={activity} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
              <defs>
                {[["sub", "#22d3ee"], ["app", "#2dd4bf"], ["rej", "#f43f5e"]].map(([id, c]) => (
                  <linearGradient key={id} id={`g-${id}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={c} stopOpacity={0.35} /><stop offset="100%" stopColor={c} stopOpacity={0} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid stroke="#1a2a42" vertical={false} />
              <XAxis dataKey="label" stroke="#6f87a6" tickLine={false} axisLine={false} fontSize={11} interval="preserveStartEnd" />
              <YAxis allowDecimals={false} stroke="#6f87a6" tickLine={false} axisLine={false} fontSize={11} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#8aa4c2" }} />
              <Area type="monotone" dataKey="submitted" name="Submitted" stroke="#22d3ee" fill="url(#g-sub)" strokeWidth={2} />
              <Area type="monotone" dataKey="approved" name="Approved" stroke="#2dd4bf" fill="url(#g-app)" strokeWidth={2} />
              <Area type="monotone" dataKey="rejected" name="Rejected" stroke="#f43f5e" fill="url(#g-rej)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Panel>

      <div className="grid-2">
        <Panel
          title="Salary change history"
          icon={Activity}
          subtitle="Applied changes (% per change)"
          actions={seededOnly && <span className="chip chip-warn">Seeded demo data</span>}
        >
          {!s ? <SkeletonRows /> : trend.length === 0 ? <Empty title="No applied salary changes yet" /> : (
            <ResponsiveContainer width="100%" height={240}>
              <ScatterChart margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                <CartesianGrid stroke="#1a2a42" />
                <XAxis dataKey="t" type="number" domain={["auto", "auto"]} stroke="#6f87a6" fontSize={11}
                  tickFormatter={(t) => new Date(t).toLocaleDateString(undefined, { month: "short", year: "2-digit" })} />
                <YAxis dataKey="pct_change" unit="%" stroke="#6f87a6" fontSize={11} />
                <ZAxis range={[60, 60]} />
                <Tooltip {...tooltipStyle} formatter={(v, n) => (n === "pct_change" ? fmtPct(v) : v)}
                  labelFormatter={() => ""} content={({ payload }) => payload?.[0] ? (
                    <div className="tt">
                      <strong>{payload[0].payload.employee}</strong>
                      <div>{payload[0].payload.department} · {payload[0].payload.date}</div>
                      <div className="mono">{fmtPct(payload[0].payload.pct_change)}</div>
                      <div className="muted">{payload[0].payload.source === "seed_demo" ? "Seeded demo data" : "Approved request"}</div>
                    </div>
                  ) : null} />
                <Scatter data={trend.filter((d) => d.source === "seed_demo")} fill="#5b708c" name="Seeded demo" />
                <Scatter data={trend.filter((d) => d.source !== "seed_demo")} fill="#22d3ee" name="Approved request" />
              </ScatterChart>
            </ResponsiveContainer>
          )}
          <p className="muted small">Grey = seeded demo history · cyan = changes approved in this system.</p>
        </Panel>

        <Panel title="Security alerts" icon={Siren} subtitle="Pending High/Critical requests needing enhanced review">
          {requests.loading ? <SkeletonRows /> : alerts.length === 0 ? <Empty title="No open high-risk alerts">Pending requests are all Low or Medium risk.</Empty> : (
            <ul className="alerts">
              {alerts.map((r) => (
                <li key={r.id}>
                  <button className="alert-item" onClick={() => setOpenId(r.id)}>
                    <div className="alert-top">
                      <RiskBadge level={r.risk_level} score={r.risk_score} />
                      <span className="mono small muted">#{r.id} · {fmtDate(r.created_at)}</span>
                    </div>
                    <strong>{r.employee_name} · <span className="mono">{fmtPct(r.pct_change)}</span></strong>
                    <span className="small muted">{(r.risk_assessment?.explanations || []).slice(0, 2).join(" ")}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Recent requests" icon={Clock} actions={<>
        <button className="btn btn-ghost btn-sm" onClick={() => go("requests")}>View all</button>
        <button className="btn btn-ghost btn-sm" onClick={onRefresh}>Refresh</button>
      </>}>
        <div className="filters">
          <label className="search-box"><Search size={15} aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by employee, code, department or #id" aria-label="Filter recent requests" />
          </label>
          <select value={statusF} onChange={(e) => setStatusF(e.target.value)} aria-label="Status filter">
            <option value="all">All statuses</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
          </select>
          <select value={riskF} onChange={(e) => setRiskF(e.target.value)} aria-label="Risk filter">
            <option value="all">All risk levels</option>{["Low", "Medium", "High", "Critical"].map((l) => <option key={l}>{l}</option>)}
          </select>
        </div>
        {requests.error ? <ErrorBox error={requests.error} onRetry={requests.reload} /> : requests.loading ? <SkeletonRows /> :
          recent.length === 0 ? <Empty title="No requests match these filters" /> : <RequestTable rows={recent} onOpen={setOpenId} />}
      </Panel>

      {canAudit && (
        <Panel title="Recent audit activity" icon={Activity} actions={<button className="btn btn-ghost btn-sm" onClick={() => go("audit")}>Open audit log</button>}>
          {audit.loading ? <SkeletonRows /> : audit.error ? <ErrorBox error={audit.error} /> : (
            <ul className="audit-mini">
              {(audit.data?.events || []).length === 0 && <li className="muted small">No audit events yet.</li>}
              {(audit.data?.events || []).map((e) => (
                <li key={e.id}>
                  <span className={`outcome o-${e.outcome}`}>{e.outcome}</span>
                  <span className="mono">{e.action}</span>
                  <span className="muted">{e.actor}{e.actor_role ? ` · ${e.actor_role}` : ""}</span>
                  <span className="muted small mono" title={fmtDate(e.timestamp)}>{fmtRelative(e.timestamp)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      <RequestDrawer requestId={openId} onClose={() => setOpenId(null)} onChanged={onRefresh} />
    </div>
  );
}
