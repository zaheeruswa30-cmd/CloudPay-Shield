import { useEffect, useMemo, useState } from "react";
import { Filter, ListChecks, RefreshCw, Search } from "lucide-react";
import { useApi, useAuth } from "../context";
import { ErrorBox, Panel, SkeletonRows } from "../components/ui";
import RequestTable from "../components/RequestTable";
import RequestDrawer from "../components/RequestDrawer";

export default function Requests({ refreshKey, onRefresh, go, param, query: route = {} }) {
  const { user } = useAuth();
  const [status, setStatus] = useState(route.status || "");
  const [risk, setRisk] = useState("");
  const [search, setSearch] = useState(route.q || "");
  const [debounced, setDebounced] = useState(route.q || "");
  const openId = param ? Number(param) : null;
  const setOpenId = (id) => go("requests", id, route.q ? { q: route.q } : undefined);
  useEffect(() => { if (route.q !== undefined) setSearch(route.q); }, [route.q]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (status) p.set("status", status);
    if (risk) p.set("risk_level", risk);
    if (debounced) p.set("search", debounced);
    const qs = p.toString();
    return `/salary-change-requests${qs ? `?${qs}` : ""}`;
  }, [status, risk, debounced]);

  const { data, loading, error, reload } = useApi(query, [refreshKey]);
  const title = user.role === "manager" ? "Review queue" : "Salary change requests";

  return (
    <div className="page">
      <Panel
        title={title}
        icon={ListChecks}
        subtitle={user.role === "manager" ? "Open a request to see its risk explanation and record a decision." : "Click a row for full risk details."}
        actions={<button className="btn btn-ghost btn-sm" onClick={() => { reload(); onRefresh?.(); }}><RefreshCw size={14} /> Refresh</button>}
      >
        <div className="filters">
          <label className="search">
            <Search size={15} aria-hidden />
            <input placeholder="Search employee, code or department" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search requests" />
          </label>
          <label className="select">
            <Filter size={14} aria-hidden />
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label className="select">
            <select value={risk} onChange={(e) => setRisk(e.target.value)} aria-label="Filter by risk level">
              <option value="">All risk levels</option>
              <option>Low</option>
              <option>Medium</option>
              <option>High</option>
              <option>Critical</option>
            </select>
          </label>
          {data && <span className="muted small">{data.length} result{data.length === 1 ? "" : "s"}</span>}
        </div>
        {error ? <ErrorBox error={error} onRetry={reload} /> : loading && !data ? <SkeletonRows rows={5} /> : <RequestTable rows={data} onOpen={setOpenId} />}
      </Panel>
      <RequestDrawer requestId={openId} onClose={() => setOpenId(null)} onChanged={() => { reload(); onRefresh?.(); }} />
    </div>
  );
}
