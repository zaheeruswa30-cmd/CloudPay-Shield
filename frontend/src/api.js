// Small fetch wrapper. The token lives in sessionStorage (cleared when the tab closes).
// Note: any XSS on this origin could read it; production should prefer HttpOnly cookies.
const BASE = import.meta.env.VITE_API_BASE || "/api";
const TOKEN_KEY = "cps_token";

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = tokenStore.get();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the CloudPay Shield API. Is the backend running on port 8000?");
  }

  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!res.ok) {
    const message = (data && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))) || `Request failed (${res.status})`;
    if (res.status === 401 && auth && token && !path.startsWith("/auth/")) onUnauthorized(message);
    throw new ApiError(res.status, message, data);
  }
  return data;
}

export const fmtPKR = (n) =>
  n === null || n === undefined || Number.isNaN(Number(n))
    ? "—"
    : `PKR ${Number(n).toLocaleString("en-PK", { maximumFractionDigits: 0 })}`;

export const fmtPct = (n) =>
  n === null || n === undefined ? "n/a" : `${n > 0 ? "+" : ""}${Number(n).toFixed(2)}%`;

export const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};

export const fmtRelative = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.round(s / 86400)} d ago`;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
};

export const pctChange = (current, proposed) => {
  const c = Number(current), p = Number(proposed);
  if (!Number.isFinite(c) || !Number.isFinite(p) || c <= 0) return null; // zero/negative/invalid: undefined change
  return ((p - c) / c) * 100;
};

export const ROLE_LABEL = {
  employee: "Employee", hr: "HR officer", manager: "Payroll manager", auditor: "Auditor", admin: "Security admin",
};

/** Download rows as CSV (client-side, from data already authorised for this user). */
export function downloadCsv(filename, rows, columns) {
  const esc = (v) => {
    const s = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    // Neutralise spreadsheet formula injection.
    const safe = /^[=+\-@]/.test(s) ? `'${s}` : s;
    return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
  };
  const lines = [columns.map((c) => c.label).join(","), ...rows.map((r) => columns.map((c) => esc(c.get(r))).join(","))];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
