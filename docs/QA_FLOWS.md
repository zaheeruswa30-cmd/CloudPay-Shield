# Browser QA flows

These flows were run in a real Chromium browser (Playwright) against the running app (FastAPI on port 8000, Vite on port 5173), starting from a **fresh sandbox database** created automatically by the backend. They were run in a Linux sandbox, not on Windows.

Result of the last run: **all flows passed with no JavaScript errors.** The only browser console messages were expected HTTP responses: a 401 from a deliberately wrong password, and 404s from "My salary" for accounts that are not linked to an employee record.

Backend: `63 passed` (`.\run-tests.ps1`). Frontend: `npx vite build` succeeds (bundle-size warning only).

## Flow 1: landing, registration and sign-in

| Step | Expected | Result |
|---|---|---|
| Open `/` | Landing page with nav, hero, problem, features, how it works, anomaly explanation, security, footer | Pass |
| Create account with a weak password | Live password rules, submit blocked | Pass |
| Create account with a valid password | Success panel, account role is **employee** | Pass |
| Sign in with a wrong password | Generic error, no username disclosure (401) | Pass |
| Sign in correctly | Redirect into the console; employee only sees employee pages | Pass |
| Visit a protected page while signed out | Sent to sign-in, then returned to the original page | Pass |

## Flow 2: HR

| Step | Expected | Result |
|---|---|---|
| Dashboard | Summary cards, risk gauge, status, distribution and activity charts with live API data | Pass |
| New request | Current salary shown, % change calculated, live risk preview with explanations | Pass |
| Reason under 5 characters | Submit blocked with a message | Pass |
| Second request for the same employee | Duplicate pending request warning | Pass |
| Submit | Confirmation dialog with score, then confirmation panel; salary **not** changed | Pass |
| Employees | Search, department filter, details drawer with salary history | Pass |
| Global search | Opens the request list filtered by the search text (empty state when nothing matches) | Pass |
| Anomaly detection | Method strip, disclaimer, filters, indicator chart, detail panel | Pass |

## Flow 3: manager

| Step | Expected | Result |
|---|---|---|
| First sign-in | MFA banner; set up authenticator, enter code, recovery codes shown | Pass |
| Sign in again | Password, then a 6-digit code | Pass |
| Approve with a short reason | Approve button disabled | Pass |
| Approve with a valid reason | Confirm dialog, request approved, salary updated, new salary version | Pass |
| Reject a Critical request with 16 characters | Reject disabled (20+ needed for High/Critical) | Pass |
| Reject with a valid reason | Request rejected, salary unchanged | Pass |

## Flow 4: notifications, auditor and admin

| Step | Expected | Result |
|---|---|---|
| HR notification bell | Shows decisions; clicking opens `#/requests/<id>` | Pass |
| Employee requests auditor access | Justification of 20+ characters required; request listed as pending | Pass |
| Auditor audit page | Filter, expand an event (hashes), CSV export, **Verify chain** reports the chain intact | Pass |
| Admin first sign-in | MFA required; enrol authenticator | Pass |
| Approve the access request | Reason required; role becomes auditor; user notified; audit event | Pass |
| Change a role from the users table | Reason and confirmation; own-role button disabled | Pass |
| Admin security page | "Disable MFA" not offered for admin | Pass |

## Responsive checks

At 1440×900 and 375×812: landing, sign-in, dashboard, review queue, request drawer, employees, anomaly detection, audit, risk policy, account and admin pages. No horizontal overflow at 375 px (page width equals viewport). The sidebar becomes a slide-in menu on mobile.

Issues found and fixed during QA: dashboard variable used before it was set; the risk badge in the confirm dialog; sidebar logo wrapping; back-link layout; a global `nav` style that stacked the landing navigation links vertically; status badge stretched across the drawer; sign-in form pushed too far down on mobile.
