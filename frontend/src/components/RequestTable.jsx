import { GitCompareArrows } from "lucide-react";
import { fmtDate, fmtPKR, fmtPct } from "../api";
import { Empty, RiskBadge, StatusBadge } from "./ui";

export default function RequestTable({ rows, onOpen, showRisk = true }) {
  if (!rows || rows.length === 0) return <Empty title="No matching requests" />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Employee</th>
            <th className="num">Current</th>
            <th className="num">Proposed</th>
            <th className="num">Change</th>
            {showRisk && <th>Risk</th>}
            <th>Status</th>
            <th>Submitted</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} onClick={() => onOpen?.(r.id)} className={onOpen ? "clickable" : ""} tabIndex={onOpen ? 0 : undefined}
              onKeyDown={(e) => e.key === "Enter" && onOpen?.(r.id)}>
              <td className="mono muted">{r.id}</td>
              <td>
                <div className="cell-main">{r.employee_name}</div>
                <div className="cell-sub mono">{r.employee_code} · {r.department}</div>
              </td>
              <td className="num mono">{fmtPKR(r.current_salary)}</td>
              <td className="num mono">{fmtPKR(r.proposed_salary)}</td>
              <td className={`num mono ${r.pct_change > 0 ? "up" : r.pct_change < 0 ? "down" : ""}`}>{fmtPct(r.pct_change)}</td>
              {showRisk && <td><RiskBadge level={r.risk_level} score={r.risk_score} /></td>}
              <td>
                <StatusBadge status={r.status} />
                {r.is_stale && <span className="chip chip-warn" title="Salary version changed"><GitCompareArrows size={12} /> stale</span>}
              </td>
              <td className="small muted">{fmtDate(r.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
