import { useRef, useState } from "react";
import { CheckCircle2, Database, FileSpreadsheet, Send, Trash2, Upload, XCircle } from "lucide-react";
import { api, fmtPKR, fmtPct } from "../api";
import { useToast } from "../context";
import { Empty, Panel, RiskBadge, Stat } from "../components/ui";

export default function DataImport({ onRefresh }) {
  const toast = useToast();
  const fileRef = useRef(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(null);
  const [showOnly, setShowOnly] = useState("all");

  async function runPreview(filename, csv_text) {
    setBusy(true);
    setSubmitted(null);
    try {
      const r = await api("/etl/preview", { method: "POST", body: { filename, csv_text } });
      setPreview(r);
      r.summary.fatal_error ? toast.error(r.summary.fatal_error) : toast.info(`Validated ${r.summary.total_rows} rows. Nothing has been imported yet.`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadSample() {
    try {
      const s = await api("/etl/sample");
      runPreview(s.filename, s.csv_text);
    } catch (e) {
      toast.error(e.message);
    }
  }

  function onFile(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 2_000_000) return toast.error("File is larger than 2 MB.");
    const reader = new FileReader();
    reader.onload = () => runPreview(f.name, String(reader.result));
    reader.readAsText(f);
    e.target.value = "";
  }

  async function submit() {
    setBusy(true);
    try {
      const r = await api(`/etl/batches/${preview.batch_id}/submit`, { method: "POST" });
      setSubmitted(r);
      setPreview((p) => ({ ...p, status: r.status }));
      toast.success(r.detail);
      onRefresh?.();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function discard() {
    try {
      await api(`/etl/batches/${preview.batch_id}/discard`, { method: "POST" });
      toast.info("Batch discarded. No changes were made.");
      setPreview(null);
    } catch (e) {
      toast.error(e.message);
    }
  }

  const s = preview?.summary;
  const rows = (preview?.rows || []).filter((r) =>
    showOnly === "all" ? true : showOnly === "invalid" ? !r.valid : showOnly === "warn" ? r.warnings.length > 0 : ["High", "Critical"].includes(r.risk_level));

  return (
    <div className="page">
      <Panel title="Payroll file validation (ETL)" icon={FileSpreadsheet}
        subtitle="Extract → transform → validate → preview. Valid rows can become pending requests; salaries are never overwritten by an import."
        actions={
          <div className="btn-row">
            <button className="btn btn-ghost btn-sm" onClick={loadSample} disabled={busy}><Database size={14} /> Use sample file</button>
            <button className="btn btn-primary btn-sm" onClick={() => fileRef.current?.click()} disabled={busy}><Upload size={14} /> Upload CSV</button>
            <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={onFile} />
          </div>
        }>
        <p className="muted small">Required columns: <span className="mono">employee_code, full_name, department, current_salary, proposed_salary, effective_date, reason</span></p>
        {!preview && <Empty title="No file validated yet">Load the fictional sample or upload your own CSV.</Empty>}
        {s && (
          <>
            <div className="stats compact">
              <Stat label="Rows" value={s.total_rows} />
              <Stat label="Valid" value={s.valid_rows} tone="ok" />
              <Stat label="Invalid" value={s.invalid_rows} tone="crit" />
              <Stat label="Warnings" value={s.rows_with_warnings} tone="warn" />
              <Stat label="Duplicates" value={s.duplicate_rows} tone="high" />
              <Stat label="Suspicious" value={s.suspicious_rows} tone="crit" hint="High/Critical risk" />
            </div>
            {s.fatal_error && <div className="banner banner-crit">{s.fatal_error}</div>}
            <div className="filters">
              {[["all", "All rows"], ["invalid", "Invalid"], ["warn", "Warnings"], ["risk", "Suspicious"]].map(([k, l]) => (
                <button key={k} className={`chip-btn ${showOnly === k ? "active" : ""}`} onClick={() => setShowOnly(k)}>{l}</button>
              ))}
              <span className="spacer" />
              {preview.status === "previewed" ? (
                <>
                  <button className="btn btn-ghost btn-sm" onClick={discard}><Trash2 size={14} /> Discard</button>
                  <button className="btn btn-primary btn-sm" disabled={busy || s.submittable_rows === 0} onClick={submit}>
                    <Send size={14} /> Submit {s.submittable_rows} valid row{s.submittable_rows === 1 ? "" : "s"} for approval
                  </button>
                </>
              ) : <span className="chip">Batch {preview.status}</span>}
            </div>
            {submitted && <div className="banner banner-ok"><CheckCircle2 size={16} /> {submitted.detail} Request IDs: {submitted.created_request_ids.join(", ") || "none"}.</div>}
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Row</th><th>Employee</th><th className="num">System salary</th><th className="num">Proposed</th><th className="num">Change</th><th>Risk</th><th>Validation</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.row_number} className={!r.valid ? "row-invalid" : ""}>
                      <td className="mono muted">{r.row_number}</td>
                      <td><div className="cell-main">{r.full_name || "—"}</div><div className="cell-sub mono">{r.employee_code || "—"}</div></td>
                      <td className="num mono">{fmtPKR(r.system_current_salary)}</td>
                      <td className="num mono">{fmtPKR(r.proposed_salary)}</td>
                      <td className="num mono">{fmtPct(r.pct_change)}</td>
                      <td>{r.risk_level ? <RiskBadge level={r.risk_level} score={r.risk_score} /> : <span className="muted">—</span>}</td>
                      <td className="small">
                        {r.valid ? <span className="ok-text"><CheckCircle2 size={13} /> valid</span> : null}
                        {r.errors.map((e, i) => <div key={i} className="crit-text"><XCircle size={13} /> {e}</div>)}
                        {r.warnings.map((w, i) => <div key={i} className="warn-text">⚠ {w}</div>)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}
