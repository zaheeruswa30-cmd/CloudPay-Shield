# CloudPay Shield

Payroll security console with risk scoring for salary changes. HR submits salary changes, a rule-based risk engine explains what looks unusual, a different person (a manager with MFA) approves or rejects, and every action goes into a SHA-256 hash-chained audit trail.

> The risk score (0–100) is a rule-based review priority. It is **not** a probability of fraud. A High or Critical score means "review carefully". It never rejects a request or accuses anyone automatically.

- Backend: Python 3.14 · FastAPI · SQLAlchemy 2 · SQLite (`backend/cloudpay_shield.db`)
- Frontend: React 19 · Vite 7 · Recharts · lucide-react
- Ports: backend `http://127.0.0.1:8000`, frontend `http://localhost:5173`

---

## 1. Prerequisites (Windows)

| Tool | Version | Check in PowerShell |
|---|---|---|
| Python | 3.12 or newer (built and tested on 3.14) | `python --version` |
| Node.js | 20.19+ or 22.12+ (Vite 7 needs this) | `node --version` |
| VS Code | any recent version | — |

This project uses its **own** database file, `backend/cloudpay_shield.db`. It does not read, change or delete your older project or its `cloudpay.db`.

## 2. First-time setup (one command)

Open the project folder in VS Code (**File → Open Folder…**), then open a terminal (**Terminal → New Terminal**, PowerShell):

```powershell
# Allow local scripts for this terminal session only (does not change system policy)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\setup.ps1
```

`setup.ps1` will:
1. create `backend\.venv` and install `backend\requirements.txt`
2. create `backend\.env` with random local secrets (only if it does not exist yet)
3. create `backend\cloudpay_shield.db` and add fictional demo data **only if the database has no users yet**. An existing database is never reset.
4. run `npm install` in `frontend\`

## 3. Run the app

Use two terminals (or **Terminal → Run Task…** in VS Code):

```powershell
# Terminal 1
.\start-backend.ps1      # http://127.0.0.1:8000  (API docs: /docs)

# Terminal 2
.\start-frontend.ps1     # http://localhost:5173
```

Run the tests (they use temporary databases and never touch `cloudpay_shield.db`):

```powershell
.\run-tests.ps1
```

## 4. Using the web application

Open **http://localhost:5173**. Everything below is done in the browser. You do not run Python scripts for normal use.

- **Landing page** (`#/`): what the product does, how the risk score works, security highlights, sign in / create account.
- **Create account** (`#/register`): always creates an **employee** account. Users cannot pick HR, manager, auditor or admin.
- **Sign in** (`#/login`): real credential check on the backend, then a 6-digit authenticator code if MFA is on.
- **Console** (after sign-in): sidebar with role-based pages, top bar with search, refresh, notifications and profile menu.

| Page | Route | Who sees it |
|---|---|---|
| Dashboard | `#/overview` | hr, manager, auditor, admin |
| My salary | `#/my-salary` | employee |
| Salary requests / Review queue | `#/requests`, `#/requests/<id>` | hr, manager, auditor (employees see their own) |
| New request | `#/new-request` | hr |
| Employees | `#/employees`, `#/employees/<id>` | hr, manager, auditor, admin (salaries only for hr, manager) |
| Data import | `#/import` | hr |
| Anomaly detection | `#/anomalies` | hr, manager, auditor |
| Audit & compliance | `#/audit` | auditor, manager, admin |
| Risk policy | `#/policy` | everyone signed in |
| Account & security | `#/security` | everyone (password, MFA, role access requests) |
| Administration | `#/admin` | admin |

Hiding a page in the menu is only for convenience. **Every rule is enforced again by the API** (401 = not signed in, 403 = wrong role).

### How privileged roles are granted (no command line)

1. A user creates an employee account, then opens **Account & security → Request role access**, picks HR, manager or auditor and writes a justification (20+ characters).
2. A security administrator (`admin01`) opens **Administration**, reviews the request and approves or rejects it with a reason. An MFA code is required if the admin session is not MFA-verified.
3. The decision is written to the hash-chained audit log and the user gets a notification. The backend reads the role from the database on every request, so the change applies immediately; the user sees the new menu after refreshing or signing in again.

Admins can also change a role directly, link an account to an employee record, unlock an account, reset MFA, and disable or enable an account. Each action needs a written reason. Admins cannot change their own role or disable themselves.

## 5. Demo accounts (local only, fictional data)

| Role | Username | Password | Can do |
|---|---|---|---|
| Employee | `employee01` | `EmployeeDemo!123` | See own salary (Ayesha Khan) and own requests; request role access |
| HR | `hr01` | `HrDemo!123` | Create requests, preview risk, import CSV, view employees and analytics |
| Manager | `manager01` | `ManagerDemo!123` | Approve or reject (MFA required), anomaly review, audit trail |
| Auditor | `auditor01` | `AuditorDemo!123` | Read-only: audit trail, chain verification, CSV export, analytics |
| Security admin | `admin01` | `AdminDemo!123` | Users, roles, access requests, MFA resets, unlocks (MFA required) |

All 10 employees and their salary history are **fictional**. These passwords are for local demos only. Change them or disable the accounts before deploying anywhere.

**No setup scripts are needed for data:** when the backend starts, it creates any missing tables, and it adds the demo data **only if the database has no users yet**. An existing database is never reset. To start without demo data, set `SEED_DEMO_DATA=false` in `backend\.env` before the first start.

`backend\admin.py` is still included as an **optional emergency tool** (for example if every admin account is locked). Normal role management happens in the Administration page.

## 6. Demo script (about 6 minutes)

1. **Landing page**: open `http://localhost:5173`, show the problem, how it works and the "risk score, not fraud probability" explanation.
2. **HR creates a risky change**: sign in as `hr01` → **New request** → pick *Bilal Hussain*, proposed `420000`, reason `Salary adjustment`. The percentage change and the risk preview update as you type. A confirmation dialog shows the score before anything is saved. The salary does **not** change yet.
3. **Duplicate warning**: try another request for the same employee. The form warns that a pending request already exists.
4. **Manager MFA**: sign in as `manager01`. A banner asks for MFA. **Account & security → Set up authenticator app**, scan the QR code, enter the code, save the recovery codes.
5. **Review**: click the notification bell or open **Review queue** → the request drawer shows the risk score, each indicator, the employee's other requests and salary history. Approve or reject needs a reason (10+ characters, 20+ for High/Critical) and a confirmation dialog.
6. **Anomaly detection**: shows the hybrid method (policy rules + robust statistics on history), the score, the indicators, the historical comparison and the recommended action, with a clear notice when history is limited.
7. **Auditor**: sign in as `auditor01` → **Audit & compliance** → filter, expand an event to see its hashes, export CSV, **Verify chain**.
8. **Admin**: create a new account, request auditor access from **Account & security**, then sign in as `admin01` → **Administration** → approve it.

## 7. Project structure

```
cloudpay-shield/
├─ setup.ps1 · start-backend.ps1 · start-frontend.ps1 · run-tests.ps1
├─ .vscode/                 recommended extensions, interpreter, tasks
├─ docs/                    ARCHITECTURE.md, QA_FLOWS.md
├─ backend/
│  ├─ main.py               FastAPI app, CORS, security headers; creates tables + seeds empty DB at startup
│  ├─ config.py             settings + risk policy (from .env)
│  ├─ database.py           engine, session, init_db (create missing tables only)
│  ├─ models.py             Employee, User, SalaryHistory, SalaryChangeRequest, AuditEvent,
│  │                        RevokedToken, ImportBatch, Notification, AccessRequest
│  ├─ security.py           PBKDF2 passwords, JWT, get_current_user, require_roles
│  ├─ mfa.py                TOTP, encrypted secrets, replay protection, recovery codes
│  ├─ risk_engine.py        pure, explainable risk scoring (policy + history + permission)
│  ├─ services.py           risk context, serialisers, notifications
│  ├─ audit.py              hash-chained audit events + verify_chain
│  ├─ etl.py                CSV validation (extract → transform → validate)
│  ├─ schemas.py            Pydantic input validation
│  ├─ routers/              auth, payroll, insight, admin, notification routes
│  ├─ seed.py               fictional demo data (used automatically on an empty DB)
│  ├─ admin.py              optional emergency CLI
│  ├─ sample_data/          payroll_changes_sample.csv
│  └─ tests/                63 pytest tests (temporary DB per test)
└─ frontend/
   ├─ vite.config.js        /api → http://127.0.0.1:8000 proxy
   ├─ public/               favicon, dashboard-preview.png (screenshot with fictional data)
   └─ src/
      ├─ App.jsx            hash router, protected routes, role-based sidebar, top bar
      ├─ api.js · context.jsx
      ├─ components/        ui (modal, confirm, password), Logo, TopbarMenus, risk gauge, request drawer
      └─ pages/             Landing, Login/Register, Overview, Requests, NewRequest, Employees,
                            MySalary, Anomalies, Audit, DataImport, Security, RiskPolicy, Admin
```

## 8. API

All routes except `/health`, `/auth/login`, `/auth/mfa/login` and `/auth/register` need `Authorization: Bearer <token>`. **401** = not signed in or invalid token; **403** = signed in but the role is not allowed. The frontend calls them through `/api/...`.

| Method | Route | Roles |
|---|---|---|
| GET | `/health` | public |
| POST | `/auth/login` | public (returns `mfa_required` + temporary token if MFA is on) |
| POST | `/auth/mfa/login` | holder of an `mfa_pending` token |
| POST | `/auth/register` | public, always creates an **employee** |
| POST | `/auth/logout` | any (revokes the token) |
| GET | `/me` | any |
| POST | `/auth/change-password` | any (current password required; signs you out) |
| POST | `/auth/mfa/setup` · `/auth/mfa/enable` · `/auth/mfa/disable` | any (managers and admins cannot disable) |
| GET | `/notifications` · POST `/notifications/{id}/read` · `/notifications/read-all` | any (own notifications only) |
| GET | `/salary/me` | employee (own linked record only) |
| GET | `/employees` · `/employees/{id}` | hr, manager, auditor, admin (salary fields only for hr, manager) |
| GET | `/risk/policy` | any signed-in user |
| POST | `/risk/assess` | hr, manager (preview, saves nothing) |
| POST | `/salary-change-requests` | hr |
| GET | `/salary-change-requests` · `/{id}` | hr, manager, auditor (employee: own, limited fields) |
| POST | `/salary-change-requests/{id}/decision` | manager, with MFA |
| GET | `/audit-events` | auditor, manager, admin (filters: search, action, outcome, actor, request) |
| GET | `/audit/verify` | auditor, manager, admin |
| GET | `/analytics/summary` | hr, manager, auditor |
| GET | `/etl/sample` · POST `/etl/preview` · `/etl/batches/{id}/submit` · `/discard` | hr |
| POST | `/access-requests` · GET `/access-requests/mine` · POST `/access-requests/{id}/cancel` | any signed-in user (own requests) |
| GET | `/admin/users` · `/admin/access-requests` | admin |
| POST | `/admin/users/{id}/role` · `/link-employee` · `/unlock` · `/reset-mfa` · `/status` | admin, with MFA, reason required |
| POST | `/admin/access-requests/{id}/decision` | admin, with MFA, reason required |

Interactive docs: `http://127.0.0.1:8000/docs`.

## 9. Risk engine (policy `2026.10-v1`)

```
percentage_change = ((proposed_salary - current_salary) / current_salary) * 100
```
A current salary that is zero, negative, missing or not a number never causes a division error. It triggers **Invalid current salary** instead.

Points for each triggered indicator are added and capped at 100. Levels: **Low 0–24 · Medium 25–49 · High 50–74 · Critical 75–100**.

| Indicator | Type | Points |
|---|---|---|
| Large salary increase (> 25 %) | policy | 25 |
| Very large salary increase (> 50 %, replaces the above) | policy | 40 |
| Unusual salary decrease (> 10 %) | policy | 20 |
| Severe salary decrease (> 30 %, replaces the above) | policy | 35 |
| Proposed salary equals current salary | policy | 10 |
| Missing or too-short reason (< 15 characters) | policy | 20 |
| Vague reason ("adjustment", "update", …) | policy | 10 |
| Duplicate pending request | policy | 20 |
| Repeated unresolved requests (30 days) | policy | 10 |
| Based on an outdated salary version | policy | 25 |
| Below payroll minimum | policy | 30 |
| Above payroll maximum | policy | 15 |
| Invalid current salary | policy | 30 |
| Submitted by an unauthorized role | permission | 40 |
| Unusual compared with salary history | history | 15 |
| Repeated large changes for this employee | history | 10 |
| Not enough history for statistical comparison | history | 0 (information only) |

**History check (the "ML-style" part, honestly described):** a robust z-score `0.6745 × (change − median) / max(MAD, 1)` compared with past applied changes in the same department, or the whole organisation if the department has fewer than 5. It is flagged when |z| > 3. This is a transparent statistical baseline, not a trained model. The demo history is **seeded demo data** and is labelled that way in the UI.

Thresholds can be changed in `backend\.env` (`RISK_INCREASE_THRESHOLD_PCT`, etc.). Each request stores the policy version and the full explanation that was used at the time.

## 10. Security: what is implemented

- PBKDF2-SHA256 password hashing (390,000 iterations, per-user salt); password policy for new accounts (12+ characters, 3 of 4 character types).
- JWT access tokens (30 min) with `jti`; logout revokes the token on the server.
- Login protection: 5 failures lock an account for 5 minutes; 20 failures per IP in 5 minutes are throttled. Error messages do not reveal whether a username exists.
- Backend RBAC on every route (`require_roles`), and denied attempts are audited as `access_denied`.
- TOTP MFA (RFC 6238): secrets encrypted at rest (Fernet), code replay blocked, 8 single-use hashed recovery codes, lock after 5 wrong codes. Managers **must** have MFA and an MFA-verified session (or give a fresh code) to decide.
- Approval workflow: separation of duties (no self-approval → 403), one decision only (→ 409), salary-version check (stale → 409), and a detailed reason for High/Critical (→ 422). Status, salary, history and audit are updated in one transaction with conditional `UPDATE`s.
- Audit trail: each event stores `SHA-256(canonical JSON of its fields + previous hash)`, and `/audit/verify` recomputes the whole chain. Passwords, tokens, MFA secrets and codes are never stored in audit details.
- ETL never writes salaries; valid rows become normal pending requests that go through the same risk scoring and approval.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store`), restricted CORS (GET/POST only), sanitised validation errors.
- Frontend keeps the token in `sessionStorage` (cleared when the tab closes). The UI hides buttons by role, but **the backend is the real control**.

## 11. Limitations (be upfront about these in a demo)

- **Not production-ready.** SQLite, a single process and local secrets in `.env` are fine for a hackathon, not for real payroll.
- The audit chain lives **in the same database**. It detects editing, deleting or reordering of events, but someone with full write access could rebuild the entire chain. For stronger guarantees, regularly copy the latest hash somewhere else (an email, a ticket, a WORM bucket).
- Rate limiting and the token revocation list are per-process and in the database; they are not shared across servers.
- The risk engine is rules plus simple statistics on **seeded demo history**. Its thresholds are not calibrated on real payroll data, and it can produce false positives and false negatives.
- The token is in `sessionStorage`, so a successful XSS attack could read it. The production choice is an HttpOnly, SameSite cookie with CSRF protection.
- No email verification or password reset by email. Notifications are in-app only.
- Most salary history is **seeded demo data**, so the statistical comparison is limited. The app says so when there is not enough history.
- The production frontend bundle is one ~800 kB file (Vite shows a size warning). Code-splitting is possible future work.
- No encryption of the SQLite file at rest (use disk encryption, or a managed database).
- Times are stored in UTC and shown in the browser's local time zone.
- Tested in a Linux sandbox (Python 3.14, Node 20) with a real browser. The PowerShell scripts were written for Windows, but were **not run on Windows** by the author of this build. Please report any path or permission issue.

## 12. Production hardening (future work)

PostgreSQL with migrations (Alembic) · HttpOnly cookies + CSRF · a secrets manager · HTTPS reverse proxy · central rate limiting (Redis) · external audit hash anchoring · SSO (OIDC) for staff · email-verified registration and password reset · encrypted backups · a model trained on real, consented history with drift monitoring · four-eyes rule for Critical changes · alerts (email/Slack) for Critical requests.

## 13. Using your old project's data

This build is a separate, complete project. Your original folder and `cloudpay.db` stay as they are. If you later want to move real records into this database, do it as a reviewed, one-way copy from a **backup** of `cloudpay.db`, never the live file. Ask for a migration script and test it on a copy first.
