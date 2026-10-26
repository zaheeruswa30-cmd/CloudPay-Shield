import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, CheckCheck, ChevronDown, KeyRound, LogOut, ShieldAlert, ShieldCheck, UserCircle2 } from "lucide-react";
import { api, fmtRelative, ROLE_LABEL } from "../api";
import { useAuth } from "../context";

function useOutsideClose(open, setOpen) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open, setOpen]);
  return ref;
}

/** Bell with unread count. Polls the backend every 30 s while the tab is open. */
export function NotificationBell({ refreshKey }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ items: [], unread: 0 });
  const [error, setError] = useState(null);
  const ref = useOutsideClose(open, setOpen);

  const load = useCallback(() => {
    api("/notifications?limit=20").then((d) => { setData(d); setError(null); }).catch(setError);
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load, refreshKey]);

  async function openItem(n) {
    if (!n.read) {
      try { await api(`/notifications/${n.id}/read`, { method: "POST" }); } catch { /* ignore */ }
    }
    setOpen(false);
    load();
    if (n.link) window.location.hash = n.link.replace(/^#/, "");
  }
  async function readAll() {
    await api("/notifications/read-all", { method: "POST" }).catch(() => {});
    load();
  }

  return (
    <div className="menu-wrap" ref={ref}>
      <button className="icon-btn bell" onClick={() => setOpen((o) => !o)} aria-label={`Notifications, ${data.unread} unread`} aria-expanded={open}>
        <Bell size={18} />
        {data.unread > 0 && <span className="bell-count mono">{data.unread > 99 ? "99+" : data.unread}</span>}
      </button>
      {open && (
        <div className="menu notif-menu" role="menu">
          <div className="menu-head">
            <strong>Notifications</strong>
            <button className="btn btn-ghost btn-xs" onClick={readAll} disabled={!data.unread}><CheckCheck size={13} /> Mark all read</button>
          </div>
          {error && <p className="small muted pad">Could not load notifications.</p>}
          {!error && data.items.length === 0 && <p className="small muted pad">You're all caught up.</p>}
          <ul className="notif-list">
            {data.items.map((n) => (
              <li key={n.id}>
                <button className={`notif ${n.read ? "" : "unread"} sev-${n.severity}`} onClick={() => openItem(n)} role="menuitem">
                  <span className="notif-dot" aria-hidden />
                  <span className="notif-text">
                    <strong>{n.title}</strong>
                    {n.body && <span className="small muted">{n.body}</span>}
                    <span className="tiny muted">{fmtRelative(n.created_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ProfileMenu({ go }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, setOpen);
  const initial = (user.full_name || user.username).slice(0, 1).toUpperCase();
  return (
    <div className="menu-wrap" ref={ref}>
      <button className="profile-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label="Profile menu">
        <span className="avatar">{initial}</span>
        <span className="profile-name">
          <strong className="small">{user.full_name || user.username}</strong>
          <span className="tiny muted">{ROLE_LABEL[user.role]}</span>
        </span>
        <ChevronDown size={15} className="muted" />
      </button>
      {open && (
        <div className="menu profile-menu" role="menu">
          <div className="profile-card">
            <span className="avatar lg">{initial}</span>
            <div>
              <strong>{user.full_name || user.username}</strong>
              <span className="small muted mono">{user.username}</span>
              <span className={`role-pill role-${user.role}`}>{ROLE_LABEL[user.role]}</span>
            </div>
          </div>
          <div className={`mfa-line small ${user.mfa_enabled ? "ok" : "warn"}`}>
            {user.mfa_enabled ? <ShieldCheck size={15} /> : <ShieldAlert size={15} />}
            MFA {user.mfa_enabled ? (user.mfa_verified_session ? "on · this session verified" : "on · session not verified") : "off"}
          </div>
          <button className="menu-item" role="menuitem" onClick={() => { setOpen(false); go("security"); }}><UserCircle2 size={16} /> Account &amp; security</button>
          <button className="menu-item" role="menuitem" onClick={() => { setOpen(false); go("security"); }}><KeyRound size={16} /> Multi-factor authentication</button>
          <button className="menu-item danger" role="menuitem" onClick={logout}><LogOut size={16} /> Sign out</button>
        </div>
      )}
    </div>
  );
}
