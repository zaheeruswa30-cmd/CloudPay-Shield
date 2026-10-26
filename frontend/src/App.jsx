import { useCallback, useEffect, useMemo, useState } from "react";
import {
  FilePlus2, FileSpreadsheet, Fingerprint, KeyRound, LayoutDashboard, ListChecks, Menu, Radar, RefreshCw,
  Scale, Search, UserCog, Users, Wallet, X,
} from "lucide-react";
import { ROLE_LABEL } from "./api";
import { useAuth } from "./context";
import { Loading } from "./components/ui";
import { Logo } from "./components/Logo";
import { NotificationBell, ProfileMenu } from "./components/TopbarMenus";
import Landing from "./pages/Landing";
import { LoginPage, RegisterPage } from "./pages/Login";
import Overview from "./pages/Overview";
import Requests from "./pages/Requests";
import NewRequest from "./pages/NewRequest";
import Employees from "./pages/Employees";
import MySalary from "./pages/MySalary";
import Audit from "./pages/Audit";
import DataImport from "./pages/DataImport";
import Security from "./pages/Security";
import RiskPolicy from "./pages/RiskPolicy";
import Anomalies from "./pages/Anomalies";
import Admin from "./pages/Admin";

// Role-aware routes. The backend enforces the same rules; hiding a link is only for usability.
const ROUTES = [
  { id: "overview", label: "Security dashboard", short: "Dashboard", icon: LayoutDashboard, roles: ["hr", "manager", "auditor"], el: Overview, section: "Monitor" },
  { id: "admin", label: "Users & access", icon: UserCog, roles: ["admin"], el: Admin, section: "Monitor" },
  { id: "my-salary", label: "My salary", icon: Wallet, roles: ["employee"], el: MySalary, section: "Monitor" },
  { id: "requests", label: "Salary requests", managerLabel: "Review queue", icon: ListChecks, roles: ["hr", "manager", "auditor"], el: Requests, section: "Payroll" },
  { id: "new-request", label: "New request", icon: FilePlus2, roles: ["hr"], el: NewRequest, section: "Payroll" },
  { id: "employees", label: "Employees", icon: Users, roles: ["hr", "manager", "auditor", "admin"], el: Employees, section: "Payroll" },
  { id: "import", label: "Data import", icon: FileSpreadsheet, roles: ["hr"], el: DataImport, section: "Payroll" },
  { id: "anomalies", label: "Anomaly detection", icon: Radar, roles: ["hr", "manager", "auditor"], el: Anomalies, section: "Investigate" },
  { id: "audit", label: "Audit & compliance", icon: Fingerprint, roles: ["auditor", "manager", "admin"], el: Audit, section: "Investigate" },
  { id: "policy", label: "Risk policy", icon: Scale, roles: ["employee", "hr", "manager", "auditor", "admin"], el: RiskPolicy, section: "Investigate" },
  { id: "security", label: "Account & security", icon: KeyRound, roles: ["employee", "hr", "manager", "auditor", "admin"], el: Security, section: "Account" },
];
const PUBLIC = ["", "home", "login", "register"];

/** Hash router: #/<page>/<param>?<query>. Hash routes work with any static server and Vite. */
function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [path, qs = ""] = raw.split("?");
  const [page = "", param = null] = path.split("/");
  return { page, param, query: Object.fromEntries(new URLSearchParams(qs)) };
}

function useHashRoute() {
  const [route, setRoute] = useState(parseHash);
  useEffect(() => {
    const on = () => { setRoute(parseHash()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = useCallback((page, param, query) => {
    const qs = query ? `?${new URLSearchParams(query)}` : "";
    window.location.hash = `/${page}${param ? `/${param}` : ""}${qs}`;
  }, []);
  return [route, go];
}

export default function App() {
  const { user, loading } = useAuth();
  const [route, go] = useHashRoute();
  const [refreshKey, setRefreshKey] = useState(0);
  const [navOpen, setNavOpen] = useState(false);
  const [q, setQ] = useState("");
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  const allowed = useMemo(() => (user ? ROUTES.filter((r) => r.roles.includes(user.role)) : []), [user]);
  const current = allowed.find((r) => r.id === route.page);

  // Protected pages: signed-out visitors go to the login page, then back to where they were heading.
  useEffect(() => {
    if (loading) return;
    if (!user && !PUBLIC.includes(route.page)) {
      sessionStorage.setItem("cps_return", window.location.hash);
      go("login");
    } else if (user && (route.page === "login" || route.page === "register")) {
      const back = sessionStorage.getItem("cps_return");
      sessionStorage.removeItem("cps_return");
      const target = back && allowed.some((r) => back.startsWith(`#/${r.id}`)) ? back : `#/${allowed[0].id}`;
      window.location.hash = target.replace(/^#/, "");
    } else if (user && !PUBLIC.includes(route.page) && !current) {
      go(allowed[0].id); // a page this role cannot use
    }
  }, [user, loading, route.page, current, allowed, go]);

  if (loading) return <div className="boot"><Loading label="Starting CloudPay Shield…" /></div>;
  if (route.page === "" || route.page === "home") return <Landing go={go} />;
  if (!user) return route.page === "register" ? <RegisterPage go={go} /> : <LoginPage go={go} />;
  if (!current) return <div className="boot"><Loading /></div>;

  const Page = current.el;
  const title = user.role === "manager" && current.managerLabel ? current.managerLabel : current.label;
  const needsMfa = user.mfa_required_for_role && !user.mfa_enabled;
  const canSearch = ["hr", "manager", "auditor"].includes(user.role);
  const sections = [...new Set(allowed.map((r) => r.section))];

  function submitSearch(e) {
    e.preventDefault();
    if (q.trim()) go("requests", null, { q: q.trim() });
  }

  return (
    <div className="shell">
      <aside className={`sidebar ${navOpen ? "open" : ""}`}>
        <div className="brand">
          <a href="#/" className="brand-link" aria-label="CloudPay Shield home"><Logo size={26} sub="Payroll Security Console" /></a>
          <button className="icon-btn nav-close" onClick={() => setNavOpen(false)} aria-label="Close menu"><X size={18} /></button>
        </div>
        <nav aria-label="Main">
          {sections.map((s) => (
            <div key={s} className="nav-section">
              <span className="nav-label">{s}</span>
              {allowed.filter((r) => r.section === s).map((r) => {
                const Icon = r.icon;
                const active = current.id === r.id;
                return (
                  <a key={r.id} href={`#/${r.id}`} className={`nav-item ${active ? "active" : ""}`}
                    onClick={() => setNavOpen(false)} aria-current={active ? "page" : undefined}>
                    <Icon size={17} aria-hidden />
                    {user.role === "manager" && r.managerLabel ? r.managerLabel : r.short || r.label}
                  </a>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="env-note tiny">
            <span className="dot ok" /> API connected · local environment
          </div>
          <span className="tiny muted">Fictional demo data only</span>
        </div>
      </aside>
      {navOpen && <div className="nav-scrim" onClick={() => setNavOpen(false)} />}

      <main className="main">
        <header className="topbar">
          <button className="icon-btn nav-open" onClick={() => setNavOpen(true)} aria-label="Open menu"><Menu size={20} /></button>
          {canSearch ? (
            <form className="global-search" onSubmit={submitSearch} role="search">
              <Search size={15} aria-hidden />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search requests by employee, code or department…" aria-label="Search salary requests" />
              <kbd className="tiny">Enter</kbd>
            </form>
          ) : <span className="spacer" />}
          <span className="spacer" />
          <button className="icon-btn" onClick={refresh} aria-label="Refresh data" title="Refresh data"><RefreshCw size={17} /></button>
          <NotificationBell refreshKey={refreshKey} />
          <ProfileMenu go={go} />
        </header>

        <div className="page-head">
          <div>
            <h1>{title}</h1>
            <span className="small muted">Signed in as {ROLE_LABEL[user.role]} · live data from the CloudPay Shield API</span>
          </div>
        </div>

        {needsMfa && current.id !== "security" && (
          <div className="banner banner-warn page-banner">
            <KeyRound size={16} /> Your role ({ROLE_LABEL[user.role]}) must enable MFA before {user.role === "admin" ? "using admin actions" : "approving or rejecting requests"}.
            <button className="btn btn-sm btn-primary" onClick={() => go("security")}>Set up MFA</button>
          </div>
        )}
        <Page key={current.id} refreshKey={refreshKey} onRefresh={refresh} go={go} param={route.param} query={route.query} />
      </main>
    </div>
  );
}
