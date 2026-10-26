import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from "lucide-react";
import { api, setUnauthorizedHandler, tokenStore } from "./api";

/* ---------------------------------------------------------------- toasts */
const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);
  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback(
    (kind, message) => {
      const id = ++idRef.current;
      setToasts((t) => [...t.slice(-3), { id, kind, message }]);
      setTimeout(() => dismiss(id), kind === "error" ? 7000 : 4500);
    },
    [dismiss]
  );
  const value = useMemo(
    () => ({
      success: (m) => push("success", m),
      error: (m) => push("error", m),
      warn: (m) => push("warn", m),
      info: (m) => push("info", m),
    }),
    [push]
  );
  const icons = { success: CheckCircle2, error: XCircle, warn: AlertTriangle, info: Info };
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => {
          const Icon = icons[t.kind];
          return (
            <div key={t.id} className={`toast toast-${t.kind}`}>
              <Icon size={18} aria-hidden />
              <span>{t.message}</span>
              <button className="icon-btn" onClick={() => dismiss(t.id)} aria-label="Dismiss notification">
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/* ---------------------------------------------------------------- auth */
const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionMessage, setSessionMessage] = useState("");

  const clear = useCallback((message = "") => {
    tokenStore.clear();
    setUser(null);
    setSessionMessage(message);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler((msg) => clear(msg || "Your session ended. Please sign in again."));
    if (!tokenStore.get()) {
      setLoading(false);
      return;
    }
    api("/me")
      .then(setUser)
      .catch(() => clear())
      .finally(() => setLoading(false));
  }, [clear]);

  const acceptToken = useCallback((resp) => {
    tokenStore.set(resp.access_token);
    setUser(resp.user);
    setSessionMessage("");
  }, []);

  const refreshMe = useCallback(async () => {
    const me = await api("/me");
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      /* token may already be invalid */
    }
    clear("You have been signed out.");
  }, [clear]);

  const value = useMemo(
    () => ({ user, loading, acceptToken, refreshMe, logout, endSession: clear, sessionMessage }),
    [user, loading, acceptToken, refreshMe, logout, clear, sessionMessage]
  );
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}
export const useAuth = () => useContext(AuthCtx);

/* ---------------------------------------------------------------- data hook */
export function useApi(path, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    api(path)
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((error) => alive && setState({ data: null, loading: false, error }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}
