import { AlertTriangle, CheckCircle2, Info, ShieldAlert } from "lucide-react";
import { RISK_COLORS, RiskBadge } from "./ui";
import { fmtPct } from "../api";

const LEVELS = [
  { name: "Low", from: 0, to: 25 },
  { name: "Medium", from: 25, to: 50 },
  { name: "High", from: 50, to: 75 },
  { name: "Critical", from: 75, to: 100 },
];

function levelOf(score) {
  return [...LEVELS].reverse().find((l) => score >= l.from)?.name || "Low";
}

/** Semicircle gauge 0-100 with coloured bands and a needle. */
export function RiskGauge({ score = 0, label = "Risk score", caption }) {
  const s = Math.max(0, Math.min(100, Number(score) || 0));
  const cx = 110, cy = 110, r = 86;
  const pt = (v, rad = r) => {
    const a = Math.PI * (1 - v / 100);
    return [cx + rad * Math.cos(a), cy - rad * Math.sin(a)];
  };
  const arc = (from, to) => {
    const [x1, y1] = pt(from);
    const [x2, y2] = pt(to);
    return `M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`;
  };
  const [nx, ny] = pt(s, r - 18);
  const level = levelOf(s);
  return (
    <figure className="gauge">
      <svg viewBox="0 0 220 132" role="img" aria-label={`${label}: ${s} of 100, ${level}`}>
        {LEVELS.map((l) => (
          <path key={l.name} d={arc(l.from + 0.6, l.to - 0.6)} stroke={RISK_COLORS[l.name]} strokeWidth="14" fill="none" opacity="0.85" />
        ))}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#e2ecf7" strokeWidth="3" strokeLinecap="round" />
        <circle cx={cx} cy={cy} r="6" fill="#e2ecf7" />
        <text x={cx} y={cy - 28} textAnchor="middle" className="gauge-num">{Math.round(s)}</text>
      </svg>
      <figcaption>
        <RiskBadge level={level} />
        <span className="muted small">{caption}</span>
      </figcaption>
      <ul className="legend" aria-label="Risk level legend">
        {LEVELS.map((l) => (
          <li key={l.name}>
            <span className="swatch" style={{ background: RISK_COLORS[l.name] }} /> {l.name} {l.from}–{l.to === 100 ? 100 : l.to - 1}
          </li>
        ))}
      </ul>
    </figure>
  );
}

const SEV_ICON = { high: ShieldAlert, medium: AlertTriangle, low: Info, info: Info };

/** Explains every indicator that contributed to a risk score. */
export function RiskBreakdown({ assessment }) {
  if (!assessment) return null;
  const triggered = assessment.indicators.filter((i) => i.points > 0);
  const info = assessment.indicators.filter((i) => i.points === 0);
  const h = assessment.historical || {};
  return (
    <div className="risk-breakdown">
      <div className="rb-head">
        <div>
          <div className="rb-score mono">{assessment.score}<span className="muted">/100</span></div>
          <RiskBadge level={assessment.level} />
        </div>
        <div className="rb-meta">
          <div><span className="muted">Change</span> <strong className="mono">{fmtPct(assessment.pct_change)}</strong></div>
          <div><span className="muted">Policy</span> <span className="mono small">{assessment.policy_version}</span></div>
        </div>
      </div>
      <p className="disclaimer">{assessment.score_label} Flags mean “review carefully”, not “fraud”.</p>

      <h3 className="h3">Why it was flagged</h3>
      {triggered.length === 0 ? (
        <div className="indicator ok">
          <CheckCircle2 size={16} aria-hidden /> <span>No policy or history indicators triggered.</span>
        </div>
      ) : (
        <ul className="indicators">
          {triggered.map((i) => {
            const Icon = SEV_ICON[i.severity] || Info;
            return (
              <li key={i.code} className={`indicator sev-${i.severity}`}>
                <Icon size={16} aria-hidden />
                <div className="ind-body">
                  <div className="ind-title">
                    {i.title} <span className="chip">{i.category}</span>
                    <span className="mono pts">+{i.points}</span>
                  </div>
                  <p>{i.explanation}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {info.map((i) => (
        <div key={i.code} className="indicator sev-info">
          <Info size={16} aria-hidden /> <p>{i.explanation}</p>
        </div>
      ))}

      <h3 className="h3">Historical comparison</h3>
      {h.reliable ? (
        <dl className="kv">
          <dt>Reference group</dt><dd>{h.reference_group} (n = {h.sample_size})</dd>
          <dt>Typical change (median)</dt><dd className="mono">{fmtPct(h.median_pct)}</dd>
          <dt>Spread (MAD)</dt><dd className="mono">{h.mad_pct} pts</dd>
          <dt>Robust z-score</dt><dd className="mono">{h.robust_z}</dd>
          <dt>Data basis</dt><dd>{h.real_samples} real · {h.seeded_demo_samples} seeded demo</dd>
        </dl>
      ) : (
        <p className="muted small">Not scored: insufficient history.</p>
      )}
      {h.note && <p className={`small ${h.seeded_demo_samples > h.real_samples ? "warn-text" : "muted"}`}>{h.note}</p>}

      <h3 className="h3">Recommended next action</h3>
      <p className="recommend">{assessment.recommended_action}</p>
    </div>
  );
}
