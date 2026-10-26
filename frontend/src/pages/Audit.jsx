import { Fragment, useEffect, useMemo, useState } from "react";
import {
  ChevronDown, ChevronRight, Download, Fingerprint, Link2, Loader2, Search, ShieldCheck, ShieldX, X,
} from "lucide-react";
import { api, downloadCsv, fmtDate } from "../api";
import { useApi, useAuth, useToast } from "../context";
import { Empty, ErrorBox, Panel, SkeletonRows } from "../components/ui";

const OUTCOMES = ["success", "denied", "failure", "blocked", "conflict", "valid", "invalid"];
const ROLES = ["employee", "hr", "manager", "auditor", "admin", "system"];
const INTEGRITY = {
  verified: { label: "Verified", cls: "ok" },
  broken: { label: "Broken", cls: "crit" },
  unverifiable: { label: "Unverifiable", cls: "warn" },
};

export default function Audit({ refreshKey, query = {} }) {
  const { user } = useAuth();
  const toast = useToast();
  const [f, setF] = useState({ search: "", action: "", outcome: "", actor_role: "", date_from: "", date_to: "", request_id: query.request || "" });
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [open, setOpen] = useState({});
  const [verify, setVerify] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  useEffect(() => { const t = setTimeout(() => setDebouncedSearch(f.search.trim()), 300); return () => clearTimeout(t); }, [f.search]);

  const path = useMemo(() => {
    const p = new URLSearchParams({ limit: "500" });
    if (debouncedSearch) p.set("search", debouncedSearch);
    for (const k of ["action", "outcome", "actor_role", "date_from", "date_to"]) if (f[k]) p.set(k, f[k]);
    if (/^\d+$/.test(f.request_id)) p.set("request_id", f.request_id);
    return `/audit-events?${p}`;
  }, [debouncedSearch, f]);
  const { data, loading, error, reload } = useApi(path, [refreshKey]);
  const events = data?.events || [];
  const chain = data?.chain;
  const anyFilter = Object.values(f).some(Boolean);

  async function runVerify() {
    setVerifying(true);
    try {
      const r = await api("/audit/verify");
      setVerify(r);
      r.valid ? toast.success(`Hash chain verified: ${r.checked} events intact.`) : toast.error(`Chain broken at event #${r.broken_at_id}.`);
      reload();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setVerifying(false);
    }
  }

  function exportCsv() {
    downloadCsv(`cloudpay-audit-${new Date().toISOString().slice(0, 10)}.csv`, events, [
      { label: "id", get: (e) => e.id }, { label: "timestamp", get: (e) => e.timestamp },
      { label: "actor", get: (e) => e.actor }, { label: "actor_role", get: (e) => e.actor_role },
      { label: "action", get: (e) => e.action }, { label: "target_type", get: (e) => e.target_type },
      { label: "target_id", get: (e) => e.target_id }, { label: "outcome", get: (e) => e.outcome },
      { label: "related_request_id", get: (e) => e.related_request_id }, { label: "integrity", get: (e) => e.integrity },
      { label: "details", get: (e) => e.details }, { label: "hash", get: (e) => e.hash },
    ]);
  }

  const v = verify || chain;
  return (
    <div className="page">
      <div className={`chain-card ${!v ? "" : v.valid ? "ok" : "crit"}`}>
        {v?.valid === false ? <ShieldX size={28} /> : <ShieldCheck size={28} />}
        <div className="chain-text">
          <strong>{!v ? "Checking audit chain…" : v.valid ? `SHA-256 hash chain intact · ${v.checked} of ${v.total} events verified` : `Chain broken at event #${v.broken_at_id}`}</strong>
          <span className="small muted">
            {v?.valid === false ? v.problem : verify ? `Last verified ${fmtDate(verify.verified_at)} by you.` : "Checked fresh every time this page loads."}
            {v?.latest_hash && <> Latest hash <span className="mono">{v.latest_hash.slice(0, 16)}…</span></>}
          </span>
        </div>
        <button className="btn btn-primary btn-sm" onClick={runVerify} disabled={verifying}>
          {verifying ? <Loader2 size={14} className="spin" /> : <Fingerprint size={14} />} Verify chain
        </button>
      </div>
      <p className="tiny muted">
        Limitation: the chain lives in the same database. It detects modified, removed or reordered events, but someone with full database access could rebuild the whole chain. Anchor the latest hash externally for stronger guarantees.
      </p>

      <Panel title="Audit events" icon={Fingerprint}
        subtitle={`${events.length} event${events.length === 1 ? "" : "s"} shown${events.length === 500 ? " (latest 500)" : ""} · details: ${data?.detail_scope || "…"}`}
        actions={<button className="btn btn-ghost btn-sm" onClick={exportCsv} disabled={!events.length}><Download size={14} /> Export CSV</button>}>
        <div className="filters wrap">
          <label className="search-box"><Search size={15} aria-hidden />
            <input value={f.search} onChange={set("search")} placeholder="Search actor, action, target or outcome" aria-label="Search audit events" />
          </label>
          <select value={f.action} onChange={set("action")} aria-label="Action">
            <option value="">All actions</option>{(data?.actions || []).map((a) => <option key={a}>{a}</option>)}
          </select>
          <select value={f.outcome} onChange={set("outcome")} aria-label="Outcome">
            <option value="">All outcomes</option>{OUTCOMES.map((o) => <option key={o}>{o}</option>)}
          </select>
          <select value={f.actor_role} onChange={set("actor_role")} aria-label="Actor role">
            <option value="">All roles</option>{ROLES.map((o) => <option key={o}>{o}</option>)}
          </select>
          <label className="date-field small">From <input type="date" value={f.date_from} onChange={set("date_from")} /></label>
          <label className="date-field small">To <input type="date" value={f.date_to} onChange={set("date_to")} /></label>
          <input className="narrow" inputMode="numeric" value={f.request_id} onChange={set("request_id")} placeholder="Request #" aria-label="Related request id" />
          {anyFilter && <button className="btn btn-ghost btn-sm" onClick={() => setF({ search: "", action: "", outcome: "", actor_role: "", date_from: "", date_to: "", request_id: "" })}><X size={14} /> Clear</button>}
        </div>

        {error ? <ErrorBox error={error} onRetry={reload} /> : loading && !data ? <SkeletonRows rows={8} /> :
          events.length === 0 ? <Empty title="No audit events match these filters" /> : (
            <div className="table-wrap">
              <table className="table audit-table">
                <thead><tr><th aria-label="Expand" /><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th className="hide-sm">Target</th><th>Outcome</th><th className="hide-sm">Request</th><th>Integrity</th></tr></thead>
                <tbody>
                  {events.map((e) => {
                    const isOpen = !!open[e.id];
                    const integ = INTEGRITY[e.integrity] || { label: e.integrity || "—", cls: "muted" };
                    return (
                      <Fragment key={e.id}>
                        <tr className={isOpen ? "open" : ""} onClick={() => setOpen((o) => ({ ...o, [e.id]: !o[e.id] }))}>
                          <td>{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                          <td className="mono small">{e.id}</td>
                          <td className="small mono nowrap">{fmtDate(e.timestamp)}</td>
                          <td><span className="cell-main">{e.actor}</span> <span className="tiny muted">{e.actor_role}</span></td>
                          <td className="mono small">{e.action}</td>
                          <td className="small muted hide-sm">{e.target_type ? `${e.target_type} ${e.target_id ?? ""}` : "—"}</td>
                          <td><span className={`outcome o-${e.outcome}`}>{e.outcome}</span></td>
                          <td className="hide-sm">{e.related_request_id && ["hr", "manager", "auditor"].includes(user.role)
                            ? <a href={`#/requests/${e.related_request_id}`} onClick={(ev) => ev.stopPropagation()}><Link2 size={12} /> #{e.related_request_id}</a>
                            : e.related_request_id ? <span className="mono small">#{e.related_request_id}</span> : <span className="muted">—</span>}</td>
                          <td><span className={`integ ${integ.cls}`}>{integ.label}</span></td>
                        </tr>
                        {isOpen && (
                          <tr className="detail-row">
                            <td colSpan={9}>
                              <div className="audit-detail">
                                <div><span className="tiny muted">Details</span><pre className="mono">{JSON.stringify(e.details || {}, null, 2)}</pre></div>
                                <div className="hashes">
                                  <span className="tiny muted">Previous hash</span><code className="mono">{e.prev_hash}</code>
                                  <span className="tiny muted">Event hash</span><code className="mono">{e.hash}</code>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
      </Panel>
    </div>
  );
}
