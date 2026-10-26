import { Scale } from "lucide-react";
import { fmtPKR } from "../api";
import { useApi } from "../context";
import { ErrorBox, Panel, RiskBadge, SkeletonRows } from "../components/ui";

export default function RiskPolicy() {
  const { data, loading, error, reload } = useApi("/risk/policy");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading) return <SkeletonRows rows={6} />;
  const t = data.thresholds;
  return (
    <div className="page grid-2 align-start">
      <Panel title="How the risk score works" icon={Scale} subtitle={`Policy ${data.policy_version}`}>
        <p className="disclaimer">{data.score_label}</p>
        <p className="small">{data.method}</p>
        <h3 className="h3">Levels</h3>
        <div className="levels">
          {data.levels.slice().reverse().map((l) => <div key={l.level}><RiskBadge level={l.level} /> <span className="mono">≥ {l.min_score}</span></div>)}
        </div>
        <h3 className="h3">Thresholds (configurable in backend/.env)</h3>
        <dl className="kv">
          <dt>Review threshold (increase)</dt><dd className="mono">{t.increase_threshold_pct}%</dd>
          <dt>Very large increase</dt><dd className="mono">{t.very_large_increase_pct}%</dd>
          <dt>Unusual / severe decrease</dt><dd className="mono">{t.decrease_threshold_pct}% / {t.severe_decrease_pct}%</dd>
          <dt>Minimum reason length</dt><dd className="mono">{t.min_reason_length} chars</dd>
          <dt>History needed for statistics</dt><dd className="mono">{t.min_history_samples} changes</dd>
          <dt>Robust z-score threshold</dt><dd className="mono">{t.robust_z_threshold}</dd>
          <dt>Payroll min / max</dt><dd className="mono">{fmtPKR(t.minimum_salary)} / {fmtPKR(t.maximum_salary)}</dd>
        </dl>
        <h3 className="h3">What happens at each level</h3>
        <p className="small">Every request requires an independent manager decision, MFA, and a current salary version. High and Critical requests are highlighted as alerts and need a detailed (20+ character) decision reason. The score never approves or rejects anything automatically.</p>
      </Panel>
      <Panel title="Indicator weights" icon={Scale}>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Indicator</th><th>Category</th><th className="num">Points</th></tr></thead>
            <tbody>
              {data.weights.map((w) => (
                <tr key={w.code}><td><div className="cell-main">{w.title}</div><div className="cell-sub mono">{w.code}</div></td><td><span className="chip">{w.category}</span></td><td className="num mono">{w.points}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
