import { useMemo, useState } from "react";
import {
  AlertTriangle, BarChart3, BrainCircuit, CheckCircle2, Clock, Database, ExternalLink, Info, Radar, Scale, ShieldAlert,
} from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtDate, fmtPKR, fmtPct } from "../api";
import { useApi, useAuth } from "../context";
import { Empty, ErrorBox, Panel, RiskBadge, SkeletonRows, Stat, StatusBadge } from "../components/ui";
import { RiskBreakdown, RiskGauge } from "../components/risk";

const tooltipStyle = {
  contentStyle: { background: "#0f1a2b", border: "1px solid #1f3350", borderRadius: 8, color: "#e2ecf7" },
  labelStyle: { color: "#8aa4c2" },
};

const triggered = (r) => (r.risk_assessment?.indicators || []).filter((i) => i.points > 0);
const hasInsufficient = (r) => (r.risk_assessment?.indicators || []).some((i) => i.code === "INSUFFICIENT_HISTORY") ||
  r.risk_assessment?.historical?.reliable === false;

function reviewStatus(r) {
  if (r.status === "pending") return { label: "Awaiting manager review", icon: Clock, cls: "warn" };
  return { label: `Reviewed: ${r.status} by ${r.decided_by || "manager"}`, icon: CheckCircle2, cls: r.status === "approved" ? "ok" : "crit" };
}

export default function Anomalies({ refreshKey, param, go }) {
  const { user } = useAuth();
  const requests = useApi("/salary-change-requests", [refreshKey]);
  const summary = useApi("/analytics/summary", [refreshKey]);
  const [level, setLevel] = useState("flagged");
  const [status, setStatus] = useState("");
  const [indicator, setIndicator] = useState("");
  const selectedId = param ? Number(param) : null;

  const all = requests.data || [];
  const indicatorOptions = useMemo(() => {
    const m = new Map();
    all.forEach((r) => triggered(r).forEach((i) => m.set(i.code, i.title)));
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [all]);

  const rows = useMemo(() => all
    .filter((r) => level === "" ? true : level === "flagged" ? ["Medium", "High", "Critical"].includes(r.risk_level) : r.risk_level === level)
    .filter((r) => !status || r.status === status)
    .filter((r) => !indicator || triggered(r).some((i) => i.code === indicator))
    .sort((a, b) => b.risk_score - a.risk_score || b.id - a.id), [all, level, status, indicator]);

  const stats = useMemo(() => ({
    flagged: all.filter((r) => ["Medium", "High", "Critical"].includes(r.risk_level)).length,
    pendingHigh: all.filter((r) => r.status === "pending" && ["High", "Critical"].includes(r.risk_level)).length,
    reviewed: all.filter((r) => r.status !== "pending" && ["High", "Critical"].includes(r.risk_level)).length,
    insufficient: all.filter(hasInsufficient).length,
  }), [all]);

  const selected = all.find((r) => r.id === selectedId) || null;
  const indicatorChart = (summary.data?.top_indicators || []).map((d) => ({ ...d, short: d.indicator.length > 22 ? `${d.indicator.slice(0, 21)}…` : d.indicator }));

  if (requests.error) return <ErrorBox error={requests.error} onRetry={requests.reload} />;

  return (
    <div className="page">
      <div className="method-strip">
        <div><Scale size={18} /><strong>Policy rules</strong><span className="small muted">Thresholds, salary bounds, reason quality, permissions</span></div>
        <div><Database size={18} /><strong>Historical patterns</strong><span className="small muted">Robust z-score against peer changes (needs enough history)</span></div>
        <div><BrainCircuit size={18} /><strong>Explainable score</strong><span className="small muted">Every point traced to a named indicator, 0–100</span></div>
      </div>
      <div className="banner banner-info small">
        <Info size={15} /> These are rule-based risk scores, not validated fraud probabilities. A flagged request is sent for investigation and human review. It is never automatically treated as fraud or rejected.
      </div>

      <div className="stats">
        {requests.loading && !requests.data ? <SkeletonRows rows={1} /> : (
          <>
            <Stat label="Flagged (Medium+)" value={stats.flagged} icon={Radar} tone="warn" />
            <Stat label="High/Critical awaiting review" value={stats.pendingHigh} icon={ShieldAlert} tone="crit" />
            <Stat label="High/Critical reviewed" value={stats.reviewed} icon={CheckCircle2} tone="ok" />
            <Stat label="Limited history" value={stats.insufficient} icon={AlertTriangle} tone="muted" hint="Historical check could not score" />
          </>
        )}
      </div>

      <div className="grid-2 align-start">
        <Panel title="Flagged requests" icon={Radar} subtitle={`${rows.length} shown · sorted by risk score`}>
          <div className="filters">
            <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Risk level">
              <option value="flagged">Medium, High &amp; Critical</option>
              <option value="">All levels</option>
              {["Low", "Medium", "High", "Critical"].map((l) => <option key={l}>{l}</option>)}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Review status">
              <option value="">Any status</option><option value="pending">Awaiting review</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
            </select>
            <select value={indicator} onChange={(e) => setIndicator(e.target.value)} aria-label="Indicator">
              <option value="">Any indicator</option>
              {indicatorOptions.map(([code, title]) => <option key={code} value={code}>{title}</option>)}
            </select>
          </div>
          {requests.loading && !requests.data ? <SkeletonRows rows={5} /> : rows.length === 0 ? <Empty title="No requests match these filters" /> : (
            <ul className="anomaly-list">
              {rows.map((r) => (
                <li key={r.id}>
                  <button className={`anomaly-item ${r.id === selectedId ? "active" : ""}`} onClick={() => go("anomalies", r.id)}>
                    <div className="alert-top">
                      <RiskBadge level={r.risk_level} score={r.risk_score} />
                      <StatusBadge status={r.status} />
                      <span className="mono small muted">#{r.id}</span>
                    </div>
                    <strong>{r.employee_name} <span className="muted small">· {r.department}</span></strong>
                    <span className="small"><span className="mono">{fmtPct(r.pct_change)}</span> · {triggered(r).length} indicator{triggered(r).length === 1 ? "" : "s"} · {fmtDate(r.created_at)}</span>
                    <span className="chips">{triggered(r).slice(0, 3).map((i) => <span key={i.code} className={`chip sev-${i.severity}`}>{i.title}</span>)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <div className="stack">
          {selected ? <AnomalyDetail r={selected} go={go} canReview={user.role === "manager"} /> : (
            <Panel title="Indicator frequency" icon={BarChart3} subtitle="How often each indicator contributed points, across all requests">
              {summary.loading ? <SkeletonRows /> : indicatorChart.length === 0 ? <Empty title="No indicators triggered yet" /> : (
                <ResponsiveContainer width="100%" height={Math.max(180, indicatorChart.length * 36)}>
                  <BarChart data={indicatorChart} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                    <CartesianGrid stroke="#1a2a42" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} stroke="#6f87a6" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis type="category" dataKey="short" width={150} stroke="#8aa4c2" fontSize={11} tickLine={false} axisLine={false} />
                    <Tooltip {...tooltipStyle} cursor={{ fill: "rgba(34,211,238,0.06)" }} labelFormatter={(_, p) => p?.[0]?.payload.indicator} />
                    <Bar dataKey="count" name="Requests" fill="#22d3ee" radius={[0, 6, 6, 0]} barSize={16} />
                  </BarChart>
                </ResponsiveContainer>
              )}
              <p className="small muted">Select a request on the left to see its full explanation.</p>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

function AnomalyDetail({ r, go, canReview }) {
  const a = r.risk_assessment;
  const rs = reviewStatus(r);
  const RsIcon = rs.icon;
  const violations = a?.policy_violations || [];
  return (
    <Panel title={`Request #${r.id} · ${r.employee_name}`} icon={ShieldAlert}
      actions={<button className="btn btn-ghost btn-sm" onClick={() => go("anomalies")}>Close</button>}>
      <div className="anomaly-head">
        <RiskGauge score={r.risk_score} caption={`${r.department} · ${r.employee_code}`} />
        <dl className="kv">
          <div><dt>Current → proposed</dt><dd className="mono">{fmtPKR(r.current_salary)} → {fmtPKR(r.proposed_salary)}</dd></div>
          <div><dt>Change</dt><dd className="mono">{fmtPct(r.pct_change)}</dd></div>
          <div><dt>Submitted by</dt><dd>{r.requested_by} · {fmtDate(r.created_at)}</dd></div>
          <div><dt>Policy violations</dt><dd>{violations.length ? violations.length : "None"}</dd></div>
          <div><dt>Review status</dt><dd className={`${rs.cls}-text`}><RsIcon size={14} /> {rs.label}</dd></div>
        </dl>
      </div>
      {r.decision_reason && <div className="reason-box"><span className="muted small">Decision reason</span><p>{r.decision_reason}</p></div>}
      {hasInsufficient(r) && (
        <div className="banner banner-warn small"><AlertTriangle size={15} /> Not enough comparable salary history to score this change statistically. The score relies on policy rules only.</div>
      )}
      <RiskBreakdown assessment={a} />
      <p className="disclaimer">Flagged for review, not a fraud finding. The score helps a person decide what to check. It is not a probability that fraud occurred.</p>
      <div className="btn-row">
        <button className="btn btn-primary" onClick={() => go("requests", r.id)}>
          <ExternalLink size={15} /> {canReview && r.status === "pending" ? "Open in review queue" : "Open request"}
        </button>
      </div>
    </Panel>
  );
}
