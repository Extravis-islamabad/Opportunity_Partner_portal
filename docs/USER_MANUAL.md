# Extravis Partner Portal — User Manual

**Version 1.0 · Applies to portal release 1.0.0**

This manual describes what the Extravis Partner Portal does, who is allowed to do
what, and how a piece of business moves through the system from a first lead to a
live licensed customer deployment.

It is written for four audiences at once — Superadmins, Channel-Manager Admins,
Partners, and Extravis Sales Reps. Each chapter states which roles it applies to.
Rules described here are the rules the software actually enforces; where the
server will refuse an action, the error code it returns is given so support staff
can match a screenshot to a cause.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Roles and the Access Model](#2-roles-and-the-access-model)
3. [Getting Started — Accounts, Login, Profile](#3-getting-started--accounts-login-profile)
4. [The Opportunity Lifecycle](#4-the-opportunity-lifecycle)
5. [Sales Stage vs Workflow Status](#5-sales-stage-vs-workflow-status)
6. [Duplicate Prevention and Multi-Partner Conflicts](#6-duplicate-prevention-and-multi-partner-conflicts)
7. [The POC Lifecycle](#7-the-poc-lifecycle)
8. [Deployment and Customer Licences (Post-PO)](#8-deployment-and-customer-licences-post-po)
9. [Deal Registration and Exclusivity](#9-deal-registration-and-exclusivity)
10. [Commissions, Tiers, Scorecard, Leaderboard](#10-commissions-tiers-scorecard-leaderboard)
11. [Sales Rep Activity Log](#11-sales-rep-activity-log)
12. [Document Requests](#12-document-requests)
13. [Knowledge Base](#13-knowledge-base)
14. [Training (LMS) and Certificates](#14-training-lms-and-certificates)
15. [Dashboards and Analytics](#15-dashboards-and-analytics)
16. [Notifications](#16-notifications)
17. [Bulk Import](#17-bulk-import)
18. [Exports](#18-exports)
19. [AI Assistance](#19-ai-assistance)
20. [Audit Logs](#20-audit-logs)
21. [Reference — Permission Matrix](#21-reference--permission-matrix)
22. [Reference — Error Codes](#22-reference--error-codes)
23. [Behaviour Notes and Known Quirks](#23-behaviour-notes-and-known-quirks)

---

## 1. System Overview

The portal is a single web application backed by one API. Everything a user sees
is one of these modules:

| Module | Purpose |
|---|---|
| **Opportunities** | The pipeline. Partners register customer opportunities; Extravis reviews and approves them. |
| **POC Tracking** | The technical evaluation an opportunity goes through before a purchase order. Five stages. |
| **Deployment** | Post-PO reality: devices and nodes deployed, licence activation and expiry. |
| **Deal Registration** | Formal claim on a customer, granting a time-boxed exclusivity window. |
| **Commissions** | Automatic payout calculation from approved deals, based on partner tier. |
| **Activity Log** | A sales rep's daily record of calls, meetings, demos, site visits. |
| **Document Requests** | Partners ask Extravis for a document; Extravis fulfils or declines. |
| **Knowledge Base** | Published collateral partners can search and download. |
| **Training (LMS)** | Courses, assessments, and completion certificates. |
| **Dashboards** | Role-specific KPIs, funnels, and analytics. |
| **Notifications** | In-app inbox plus email for events that need someone's attention. |
| **Audit Logs** | An immutable record of who changed what. Superadmin only. |

Two facts hold across every module and are worth internalising before reading further:

- **Nothing is hard-deleted.** Removal sets a `deleted_at` timestamp. Records
  disappear from lists but survive for audit.
- **Every mutation is audited.** Create, update, approve, reject, close, reopen,
  stage change — all of it lands in the audit log with the actor's user ID.

---

## 2. Roles and the Access Model

There are three roles in the database (`admin`, `partner`, `sales_rep`) and one
flag (`is_superadmin`) that sits on top of `admin`. That produces **four effective
identities**.

### 2.1 The four identities

#### Superadmin (`admin` + `is_superadmin`)

The global operator. Sees every company, every opportunity, every POC, every
licence, with no scoping filter applied anywhere. Exclusively holds:

- Creating and deleting companies
- Creating admin and sales-rep accounts
- The Users administration page
- Audit Logs
- Bulk Import (companies and opportunities)
- Editing or deleting another user's sales activity entries

The first superadmin is bootstrapped at deployment from the `SUPERADMIN_EMAIL` /
`SUPERADMIN_PASSWORD` environment variables. Change that password immediately.

#### Channel-Manager Admin (`admin`, no superadmin flag)

An Extravis channel manager. Functionally an admin, but **scoped to the companies
they channel-manage** — that is, companies whose `channel_manager_id` is their
user ID. Their scope is computed on every request; if they manage zero companies
they see nothing operational, which is deliberate and not a bug.

They can review and approve opportunities, drive POCs, manage licences, approve
deals, move commissions, fulfil document requests, publish knowledge-base
documents and courses, and create *partner* accounts for their own companies.

They cannot create admins or sales reps, cannot create or delete companies,
cannot see audit logs, cannot bulk-import, and **cannot modify another admin or
the superadmin** — those accounts have no `company_id`, so they fall outside
every channel manager's scope by construction.

#### Partner

An external partner-company user. Scoped to **their own submissions** — not their
company's. A partner sees the opportunities they personally submitted, the
document requests they raised, their own enrolments and certificates.

Partners are the only role that can *create* an opportunity or a deal
registration. They are read-only observers of POC and licence progress on their
own opportunities.

Partners never see internal notes: the field is stripped from the response before
it reaches them.

#### Sales Rep (`sales_rep`)

An Extravis sales representative. Scoped to **opportunities where they are the
assigned `sales_rep_id`**. They drive the technical side: POC stages, POC close,
licence records. They keep a daily activity log.

A sales rep is explicitly *not* a weaker admin. Modules written before the role
existed — commissions, scorecards, leaderboard, deal registration — deny sales
reps at the router with "Sales reps do not have access to this area", rather than
letting them fall through an `if partner … else admin` branch and read everything.
Document requests deny them too.

### 2.2 How scoping is enforced

Three layers, all of which must agree:

1. **Route guard** — decides whether the caller may reach the endpoint at all
   (`admin required`, `partner required`, `superadmin required`, `admin or sales
   rep`, `not a sales rep`).
2. **List scoping** — list endpoints inject a mandatory filter derived from the
   caller's role. A partner's `submitted_by` filter and a channel manager's
   company filter are forced server-side regardless of what the client asks for.
3. **Per-record check** — single-record endpoints re-check ownership against the
   record itself. For POC and licence data the check runs against the *parent
   opportunity*, because that is where ownership lives.

The per-record rule for an opportunity (and anything hanging off it) is:

| Role | May access an opportunity when… |
|---|---|
| Superadmin | always |
| Channel-Manager Admin | its `company_id` is in the companies they manage |
| Sales Rep | its `sales_rep_id` is their user ID |
| Partner | its `submitted_by` is their user ID |

### 2.3 Navigation by role

What appears in the left-hand menu:

| Menu item | Superadmin | Channel Mgr | Partner | Sales Rep |
|---|:--:|:--:|:--:|:--:|
| Dashboard | ✅ | ✅ | ✅ | ✅ |
| Companies | ✅ (all) | ✅ ("My Companies") | — | — |
| Users | ✅ | — | — | — |
| Opportunities / Pipeline | ✅ | ✅ | ✅ (own) | ✅ (assigned) |
| Duplicate Review | ✅ | ✅ | — | — |
| POC Tracking | ✅ | ✅ | ✅ (read-only) | ✅ |
| Deployment | ✅ | ✅ | — | ✅ |
| Activity Log | ✅ (any rep) | ✅ (any rep) | — | ✅ (own) |
| Deal Registration | ✅ | ✅ | ✅ | — |
| Commissions | ✅ | ✅ | ✅ (own) | — |
| My Scorecard | — | — | ✅ | — |
| Leaderboard | ✅ | ✅ | ✅ | — |
| Knowledge Base | ✅ | ✅ | ✅ | ✅ |
| Training / LMS | ✅ | ✅ | ✅ | ✅ |
| Document Requests | ✅ | ✅ | ✅ | — |
| Bulk Import | ✅ | — | — | — |
| Audit Logs | ✅ | — | — | — |
| Notifications / Profile | ✅ | ✅ | ✅ | ✅ |

Hiding a menu item is a convenience, not the security boundary. The API enforces
the same rules independently; typing a URL directly gets you a redirect to the
dashboard on the front end and a 403 from the API.

---

## 3. Getting Started — Accounts, Login, Profile

### 3.1 How accounts are created

Users do not self-register. An account is always created by someone with
authority:

- **Superadmin** creates admin, sales-rep, and partner accounts for any company.
- **Channel-Manager Admin** creates partner accounts, and only for companies they
  manage. Attempting to create an admin or sales rep is refused; attempting to
  attach a partner to an unmanaged company is refused.
- **Bulk Import** (superadmin) can create partner-company and user records as a
  side effect of ingesting a workbook.

A new account is created in `pending_activation` status with an activation token
emailed to the user. Bulk-imported accounts are created the same way — pending,
with a random unguessable password — so an import never mints an
immediately-loginable account.

### 3.2 Activation, login, lockout

| Step | Rule |
|---|---|
| Activation | The emailed link is valid for **72 hours**. The user sets their own password on activation, which flips the account to `active`. |
| Login | Rate-limited to **10 attempts per minute per IP**. |
| Failed attempts | After **5 consecutive failures** the account is set to `locked` for **30 minutes**. |
| Auto-unlock | Logging in successfully after the lockout window expires restores `active` automatically. |
| Access token | Valid **15 minutes**; the app refreshes it silently. |
| Refresh token | Valid **7 days**. Logging out blacklists both tokens immediately. |
| Password reset | "Forgot password" is rate-limited to **5 per minute**; the reset link expires after **1 hour**. Resetting a password also unlocks a locked account. |

Login failures deliberately return one generic message (`INVALID_CREDENTIALS`)
whether the email is unknown or the password is wrong, so the login form cannot be
used to enumerate valid email addresses. Distinct messages appear only for states
the user genuinely needs to act on: `ACCOUNT_NOT_ACTIVATED`, `ACCOUNT_LOCKED`,
`ACCOUNT_INACTIVE`.

### 3.3 Profile and deactivation

Every user can edit their own profile (name, job title, phone) and change their
password. Deactivation and reactivation are admin actions, subject to the same
scoping rule as everything else: a channel manager may deactivate a partner in a
company they manage, and nobody else.

### 3.4 Partner onboarding checklist (partners only)

New partners see a five-item checklist on their dashboard. Items tick themselves
as the underlying event happens:

1. Submit your first opportunity
2. Browse the knowledge base (download at least one document)
3. Enrol in a course
4. Complete your profile (set a job title)
5. Submit a document request

The partner can also dismiss the checklist by marking onboarding complete. The
checklist is informational — nothing in the portal is gated behind it.

---

## 4. The Opportunity Lifecycle

This is the core workflow. An opportunity is a customer deal a partner registers
with Extravis for approval.

### 4.1 The seven statuses

| Status | Meaning |
|---|---|
| `draft` | Created but not submitted. Visible only to its author. |
| `pending_review` | Submitted, waiting for an admin to pick it up. |
| `under_review` | An admin has it open. **Locked to the partner.** |
| `approved` | Accepted by Extravis. Terminal for the review workflow. |
| `rejected` | Declined with a written reason. The partner can fix and resubmit. |
| `removed` | Soft-deleted by an admin. Excluded from all lists and analytics. |
| `multi_partner_flagged` | Legacy status value; in practice conflicts are represented by the `multi_partner_alert` flag on an otherwise normal status. |

### 4.2 The state machine

```
                    ┌──────────────────────────────────────────┐
                    │                                          │
                    ▼                                          │
   [ create ]  ┌─────────┐   submit    ┌────────────────┐      │ submit
   partner ───►│  DRAFT  │────────────►│ PENDING_REVIEW │      │ (partner)
               └─────────┘   partner   └────────────────┘      │
                    │                          │               │
                    │                          │ admin opens   │
                    │                          │ the record    │
                    │                          ▼               │
                    │                  ┌───────────────┐       │
                    │                  │ UNDER_REVIEW  │       │
                    │                  └───────────────┘       │
                    │                     │         │          │
                    │            approve  │         │ reject   │
                    │            (admin)  │         │ (admin)  │
                    │                     ▼         ▼          │
                    │              ┌──────────┐  ┌──────────┐  │
                    │              │ APPROVED │  │ REJECTED │──┘
                    │              └──────────┘  └──────────┘
                    │
                    │  admin remove (from any status)
                    └──────────────────────► [ REMOVED ]
```

Approve and reject are both reachable directly from `pending_review` as well —
an admin does not have to mark a record under review first.

### 4.3 Transition rules in full

| Action | Who | Allowed from | Result | Refusal code |
|---|---|---|---|---|
| Create | Partner | — | `draft` or `pending_review` (partner's choice on the form) | `DUPLICATE_BLOCKED` |
| Edit | Partner (own only) | `draft`, `pending_review`, `rejected` | fields updated | `OPPORTUNITY_LOCKED` (under review / approved), `CANNOT_EDIT` |
| Submit | Partner (own only) | `draft`, `rejected` | `pending_review`, `submitted_at` stamped, rejection reason cleared, all admins notified | `CANNOT_SUBMIT`, `DUPLICATE_BLOCKED` |
| Mark under review | Admin | `pending_review` | `under_review`, reviewer recorded | `CANNOT_REVIEW` |
| **Auto** under review | Admin | `pending_review` | Happens automatically the moment an admin *opens* the detail page | — |
| Approve | Admin | `pending_review`, `under_review` | `approved`, reviewer + timestamp stamped, optional Preferred Partner tag, partner notified, tier re-evaluated | `CANNOT_APPROVE` |
| Reject | Admin | `pending_review`, `under_review` | `rejected` with a mandatory written reason, partner notified | `CANNOT_REJECT` |
| Remove | Admin | any | `removed` + soft-deleted, partner notified | — |
| Add internal note | Admin | any | note saved (invisible to partners), partner notified that *a* note was added | — |

### 4.4 The edit lock — the rule partners ask about most

A partner can edit an opportunity in `draft`, `pending_review`, or `rejected`.

The moment an admin opens the opportunity, it silently becomes `under_review` and
the partner's Edit button stops working, returning:

> **This opportunity can no longer be edited. An admin is reviewing it.**

This is intentional: it stops a record changing underneath a reviewer mid-decision.
If the partner needs a change at that point, the admin must either approve, or
reject with a reason — a rejected opportunity is editable and resubmittable again.

### 4.5 Attachments

- Up to **5 files** per opportunity (`MAX_DOCUMENTS_REACHED` beyond that).
- Maximum **20 MB** per file.
- Allowed types: PDF, Word, PowerPoint, Excel, PNG, JPEG. Anything else is
  refused with `INVALID_FILE_TYPE`.
- A partner may delete an attachment only while the opportunity is
  `pending_review` or `under_review` (`CANNOT_DELETE_DOCUMENT` otherwise).
  Admins are not restricted.
- Downloads use short-lived signed links valid for **30 minutes**. Files are never
  served as anonymous static URLs — a link copied out of the page stops working
  after half an hour.

### 4.6 What happens automatically on submit

Submitting is not just a status change. In one transaction the portal:

1. Normalises the customer name and extracts a customer domain (from the name or
   pasted into the requirements text).
2. Runs the full duplicate check. A **hard block** aborts the submission; a **soft
   warning** sets `multi_partner_alert` and lets it through.
3. Runs a second, narrower check for the exact same customer *and* opportunity name
   registered by a different company — if found, it flags **both** records and
   raises a Multi-Partner Alert to all admins.
4. Notifies every admin (in-app plus email).
5. Writes an audit entry.
6. Fires a background AI scoring job, if AI is configured. The score appears on the
   record a few seconds later; nothing waits for it.

### 4.7 What happens automatically on approval

- Reviewer and review timestamp are stamped on the record.
- The partner is notified; if Preferred Partner was ticked, a second congratulatory
  notification goes out.
- The partner company's tier is re-evaluated for a possible upgrade (see §10.4).

---

## 5. Sales Stage vs Workflow Status

This distinction confuses new users, so it deserves its own section.

**Status** (§4.1) is the *approval workflow* — where the record sits between the
partner and Extravis.

**Stage probability** is the *commercial sales stage* — how far the deal has
progressed toward money. It is a decimal from 0.1 to 1.0 stored on the
opportunity, and it drives every weighted-pipeline number in the analytics.

| Probability | Stage label |
|---|---|
| 0.1 | Raw Lead |
| 0.3 | POC Engaged / Tender Specs |
| 0.6 | POC Successful / Budget Approved |
| 0.7 | Price Submitted / Negotiation |
| 0.9 | PO Received |
| 1.0 | Payment Received |

**Weighted pipeline = Σ (worth × stage_probability).** That figure, not raw worth,
is what leadership reads on the Target Plan dashboard.

The two axes move independently. An opportunity can be `approved` (Extravis has
blessed the registration) while sitting at stage 0.3 (the POC has only just
started). Conversely a bulk-imported record at stage 0.9 arrives already
`approved`, because the importer maps commercial progress onto an initial workflow
status:

| Imported progress | Initial status |
|---|---|
| ≤ 0.15 | `draft` |
| ≤ 0.35 | `pending_review` |
| ≤ 0.65 | `under_review` |
| > 0.65 | `approved` |

That mapping applies **only at import time**. Afterwards, changing the stage
probability never moves the workflow status, and approving an opportunity never
changes its stage. Keep the stage current by editing the opportunity as the deal
progresses.

Alongside stage, three other commercial fields feed the analytics: **Product**,
**Industry**, and **Time Frame** (quarter strings such as `Q3 - 2027`, parsed into
quarter buckets for the city funnel and target-plan views).

---

## 6. Duplicate Prevention and Multi-Partner Conflicts

Two partners chasing the same customer is the problem this subsystem exists to
prevent. Detection runs on **create**, on **edit** when the customer name or
country changes, and again on **submit**.

### 6.1 The five detection layers

| Layer | What it looks for | Severity |
|---|---|---|
| 1 · Exact | Same normalised customer name + same country | Warn |
| 2 · Fuzzy | Trigram similarity ≥ 0.55 on the customer name, same country | Warn |
| 3 · Domain | Same customer domain (e.g. `atlas-mfg.com`) | Warn |
| 4 · Exclusivity | An approved deal registration with a live exclusivity window on that customer, owned by another company | **Block** |
| 5 · Ownership | An active customer-ownership record pointing at another company | **Block** |

A match only counts against you if it belongs to a **different** company. Your own
company's existing records never block or warn you.

Name normalisation strips case, whitespace, punctuation, and common corporate
suffixes, so "Atlas Manufacturing Ltd.", "atlas manufacturing limited", and
"Atlas Manufacturing" all collapse to the same key.

### 6.2 What each severity does

- **Block** → HTTP 409 `DUPLICATE_BLOCKED`. The opportunity is not created or not
  submitted. The response carries the full report, so the form can name the
  blocking company and the exclusivity end date.
- **Warn** → the record is created or submitted normally, but `multi_partner_alert`
  is set and it lands in the admin **Duplicate Review** queue.
- **Clear** → nothing happens.

### 6.3 Live checking on the form

The create form calls a read-only duplicate check as the customer name is typed,
so a partner sees the warning panel before pressing Submit rather than after. That
call mutates nothing.

### 6.4 The Duplicate Review queue (admins)

**Pipeline → Duplicate Review** lists every non-removed, non-rejected opportunity
that is either flagged `multi_partner_alert` or was linked to another record by the
AI duplicate detector. Each row shows the flagged opportunity, the record it
matched against, and whether it was flagged by `system` (rule-based) or `ai`.
Channel managers see only their own companies' rows.

From the queue an admin works the conflict the normal way: approve one, reject the
other with a reason, or remove a genuine duplicate.

### 6.5 Customer ownership

Approving a deal registration writes a **customer ownership** record: that customer
name, in that country, belongs to that partner company until the exclusivity end
date. Ownership is what makes Layer 5 fire on later submissions from other
partners. Approving a second overlapping deal for the same company extends the
existing ownership rather than duplicating it.

---

## 7. The POC Lifecycle

A POC (proof of concept) is the technical evaluation an opportunity goes through
before a purchase order. **Exactly one POC per opportunity.**

**Who can drive it:** admins (channel-manager and superadmin) and the assigned
sales rep. **Who can watch it:** the partner who submitted the opportunity, read-only.

### 7.1 The five stages

| # | Stage | Meaning |
|---|---|---|
| 1 | **VM Provisioning** | The evaluation VM is allocated. *This event starts the POC.* |
| 2 | **Deployment** | The product is deployed onto the VM. |
| 3 | **Device Onboarding** | Customer devices and nodes are connected. |
| 4 | **Dashboarding** | Dashboards are built for the customer. |
| 5 | **Fine Tuning** | Tuning and handover. |

Each stage carries its own completion date and is ticked independently. **Stages
may be completed out of order** — real POCs do run that way, and the system does
not force sequence. The only ordering rule enforced is that no stage may be
completed *before* the POC started (`STAGE_BEFORE_START`).

The "current stage" shown in lists and on the dashboard is simply the first stage
that is not yet ticked.

### 7.2 Status is derived, never chosen

You cannot set a POC's status directly. It follows from the data:

| Status | Condition |
|---|---|
| **Not Started** | No VM allocated yet |
| **Running** | VM allocated and the POC is not closed — whether 1 of 5 or 5 of 5 stages are done |
| **Successful** | Explicitly closed with a positive outcome |
| **Unsuccessful** | Explicitly closed with a negative outcome |

**Completing all five stages does not close the POC.** "The technical work is
finished" and "the customer accepted it" are different facts, and only a human
knows the second one. Someone must close it deliberately.

### 7.3 Operations

```
  [ no POC ]
      │
      │ Start POC — record VM allocation (admin / assigned sales rep)
      ▼
  ┌─────────┐   tick stages 2-5 in any order    ┌─────────┐
  │ RUNNING │◄─────────────────────────────────►│ RUNNING │
  └─────────┘                                   └─────────┘
      │
      │ Close POC — choose Successful or Unsuccessful
      ▼
  ┌──────────────────────────┐    Reopen (mistake correction)
  │ SUCCESSFUL / UNSUCCESSFUL│───────────────────────────────► RUNNING
  └──────────────────────────┘
```

**Start POC.** Requires a start date; a target end date is optional but strongly
recommended, because it is what makes "overdue" meaningful. Starting *is*
completing VM Provisioning — the two dates are held in lockstep and cannot drift
apart. Starting a POC twice is refused (`POC_ALREADY_STARTED`). A target end date
before the start date is refused (`INVALID_DATE_RANGE`).

**Tick a stage.** Set a completion date, or clear it by sending an empty date.
Clearing VM Provisioning un-starts the whole POC.

**Edit.** Target end date, notes, and any stage date can be corrected while the
POC is open. A closed POC is frozen (`POC_CLOSED`) — reopen it first.

**Close.** Requires an explicit Successful / Unsuccessful outcome. Optional
outcome notes; a failure reason is accepted only on an unsuccessful close and is
discarded on a successful one, so a stale reason from an earlier attempt cannot
linger. The end date defaults to today and cannot precede the start date. Closing a
POC that never started is refused (`POC_NOT_STARTED`).

**Reopen.** Undoes a close — for when someone closed the wrong record. It clears
the close timestamp, closer, end date, outcome notes, and failure reason, and the
status reverts to Running.

### 7.4 Overdue

A POC is **overdue** when it is still open and its target end date is in the past.
A closed POC is never overdue, however late it finished. Overdue counts appear on
the POC list, the sales-rep dashboard, and the deployment analytics.

### 7.5 What each role sees on the POC list

| Role | Rows shown |
|---|---|
| Superadmin | All POCs |
| Channel-Manager Admin | POCs on opportunities belonging to companies they manage |
| Sales Rep | POCs on opportunities assigned to them |
| Partner | POCs on their own company's opportunities — read-only, no action buttons |

---

## 8. Deployment and Customer Licences (Post-PO)

Once a purchase order lands, the opportunity stops being pipeline and becomes a
live customer deployment to be tracked. That is what the **Deployment** module and
the customer-licence record are for.

**Who can edit:** admins and the assigned sales rep. **Who can view:** the same,
plus the submitting partner (read-only). The Deployment analytics page itself is
admin and sales-rep only — partners have no menu entry for it.

### 8.1 The licence record

One licence record per opportunity, created when the PO arrives. The form is a
single upsert that gets filled in progressively as facts land:

| Field | Notes |
|---|---|
| PO number | |
| PO received date | |
| PO value | The real contracted value, which may differ from the opportunity's estimated worth |
| Device count | Devices are licensed separately from nodes |
| Node count | |
| Licence activated at | The date the licence goes live. May be in the future. |
| Licence expires at | Leave blank for a perpetual licence. Must not precede activation (`INVALID_DATE_RANGE`). |
| Licence key | |
| Notes | |

### 8.2 Licence status is derived from dates

Like POC status, licence status is computed, never chosen:

| Status | Condition |
|---|---|
| **Pending Activation** | No activation date, or the activation date is in the future |
| **Active** | Activated, and either no expiry or expiry more than 60 days away |
| **Expiring Soon** | Activated, expiry within the next **60 days** |
| **Expired** | Expiry date is in the past |

This matters operationally: a licence saved today as Active becomes Expiring Soon
and then Expired on its own as the calendar advances, with nobody touching the
record. The portal recomputes status on every read and on every filter, so a
licence can never render as "active" past its expiry. A nightly background job
also re-syncs the stored column so that anyone querying the database directly sees
sane values.

### 8.3 The Deployment page

Four headline figures — Active POCs, Devices Deployed, Nodes Deployed, Active
Licences — over four views:

- **POC stage funnel** — how many POCs have cleared each of the five stages.
- **POC activity** — POCs started vs completed per month over a rolling 12 months.
  A POC started in March and closed in June counts in both months.
- **Licences by status** — the derived breakdown.
- **Licences expiring in the next 90 days** — the renewal chase list, showing
  customer, partner, country, device/node counts, expiry date, and days remaining.

All four respect the caller's scope: a channel manager sees their companies, a
sales rep sees their assigned opportunities.

### 8.4 The end-to-end journey

Putting §4, §7, and §8 together — one deal, start to finish:

```
 PARTNER            Register opportunity ──► Draft ──► Submit
                                                          │
 SYSTEM              duplicate check · multi-partner check · AI score
                                                          │
 ADMIN               Review ──► Approve  (Preferred Partner tag optional)
                                    │
 SALES REP / ADMIN   Start POC (VM allocated)
                        └─► Deployment ─► Device Onboarding ─► Dashboarding ─► Fine Tuning
                                    │
 SALES REP / ADMIN   Close POC ──► Successful
                                    │
 PARTNER / ADMIN     (optionally) Deal registration approved ─► exclusivity + commission
                                    │
 SALES REP / ADMIN   PO received ──► licence record: devices, nodes, activation, expiry
                                    │
 SYSTEM              Licence: Pending Activation ─► Active ─► Expiring Soon ─► Expired
                                    │
 EVERYONE            Renewal chased from the Deployment expiry list
```

Throughout, the opportunity's **stage probability** should be advanced to match:
0.3 when the POC engages, 0.6 when it succeeds, 0.7 at negotiation, 0.9 on PO,
1.0 on payment. Nothing advances it for you.

---

## 9. Deal Registration and Exclusivity

Deal registration is a **partner and admin** workflow. Sales reps have no access.

A deal registration is a partner's formal claim on a named customer. Approved, it
grants a time-boxed exclusivity window during which no other partner can register
that customer.

### 9.1 The flow

| Step | Who | Detail |
|---|---|---|
| Register | Partner | Customer name, description, estimated value, expected close date. Optionally linked to an existing opportunity. |
| Conflict check | System | If another company already holds live exclusivity on that customer, the registration is refused with `EXCLUSIVITY_CONFLICT`. |
| Notify | System | All admins are alerted. |
| Approve | Admin | The admin sets the exclusivity length in days. The window runs from the approval date. |
| Reject | Admin | Requires a written reason. The partner is notified. |

Only a `pending` deal can be approved or rejected (`DEAL_NOT_PENDING`).

### 9.2 What approval triggers

1. Exclusivity start = today, end = today + the chosen number of days.
2. A **customer ownership** record is written or extended (see §6.5), which is what
   blocks other partners' opportunity submissions for that customer.
3. A **commission** is calculated automatically (see §10).
4. The partner is notified with the exclusivity length.

Steps 2 and 3 are deliberately non-blocking: if either fails, the approval still
stands and the failure is logged. An admin can chase the commission separately.

---

## 10. Commissions, Tiers, Scorecard, Leaderboard

**Available to:** admins and partners. Sales reps are denied at the router.

### 10.1 How a commission is created

One commission row per approved deal, created automatically at deal approval.
The calculation is:

> **amount = deal estimated value × tier rate %**

The partner's tier **at that moment** and the rate then in force are *snapshotted*
onto the commission row, so a later tier upgrade or a rate change never rewrites
history. Money is computed with exact decimal arithmetic, rounded to two places
(banker's rounding). Calculation is idempotent — a deal can only ever produce one
commission.

Default rates, used when no rate table has been configured:

| Tier | Rate |
|---|---|
| Silver | 5% |
| Gold | 8% |
| Platinum | 12% |

Rates are configurable per tier with effective-from / effective-to dates, so
historic rate changes are auditable without touching past commissions.

### 10.2 Commission status

```
   PENDING ──► APPROVED ──► PAID
      │            │
      └────────────┴──► VOID
```

| From | Allowed to |
|---|---|
| Pending | Approved, Void |
| Approved | Paid, Void |
| Paid | *(terminal)* |
| Void | *(terminal)* |

Only an **admin** can move a commission. Anything else returns `INVALID_TRANSITION`.
The recipient is notified in-app on every transition. Approving stamps
`approved_at`; marking paid stamps `paid_at` (and backfills `approved_at` if a
commission was jumped straight to paid).

Partners see their own commissions; channel managers see their companies';
superadmins see all.

### 10.3 Statements

Monthly rollups per company, aggregating approved and paid commissions in the
period, downloadable as PDF. Partners can pull their own; admins can pull those in
scope.

### 10.4 Partner tiers

Three tiers: **Silver → Gold → Platinum**. Tier drives the commission rate and is
displayed as a badge next to the partner's company name.

Tier upgrades are evaluated automatically whenever an opportunity is approved and
whenever a partner completes a course. The rule actually applied:

| Tier awarded | Requires |
|---|---|
| Platinum | ≥ 20 approved opportunities **and** ≥ 80% LMS completion rate |
| Gold | ≥ 10 approved opportunities **and** ≥ 50% LMS completion rate |
| Silver | default |

**Upgrades only.** The evaluation never demotes a company. Each change writes a
tier-history row recording the previous tier, the new tier, and the reason.

> ⚠ Note that the *progress bars* shown on the partner dashboard and the scorecard
> use different, more optimistic thresholds than the engine that actually performs
> the upgrade. See §23.1.

### 10.5 Scorecard and Leaderboard

**My Scorecard** (partners only) shows the company's tier, progress toward the
next tier, approved deal count and value, commission earned vs paid, a six-month
commission trend, achievement badges, and the company's leaderboard rank.

**Leaderboard** (partners and admins) ranks companies by total approved-and-paid
commission.

---

## 11. Sales Rep Activity Log

**Sales reps only** create entries. **Admins** read any rep's log. **Partners have
no access at all.**

Each entry is one activity a rep performed on one working day:

| Field | Notes |
|---|---|
| Date | **Weekdays only** (Monday–Friday) and **never in the future** — `INVALID_ACTIVITY_DATE` |
| Type | Call · Meeting · Demo · Email · Site Visit · Follow-up · Training · Other |
| Customer name | Free text — not every call maps to a portal opportunity |
| Opportunity | Optional link to a real opportunity; the link is validated |
| Duration | Minutes |
| Notes | Free text |

The view is a **Monday–Friday month grid**. Reps log several entries per day; the
page also shows per-type totals and total minutes for the month.

**Who may edit or delete an entry:**

| Actor | Permission |
|---|---|
| The rep who logged it | Edit and delete their own entries |
| Superadmin | Edit and delete anyone's entry |
| Channel-Manager Admin | **Read only** — "Only superadmins can modify sales rep activities" |
| Partner | No access |

Reading another user's month is restricted to *sales rep* targets only, so the
`user_id` parameter cannot be used to resolve arbitrary user IDs to names. An admin
viewing the page without picking a rep sees their own (usually empty) log.

---

## 12. Document Requests

A partner needs a document Extravis has not published. They raise a request; an
admin fulfils or declines it.

| Step | Who | Detail |
|---|---|---|
| Raise | Partner | Description, reason, urgency (Low / Medium / High). The partner must belong to a company (`NO_COMPANY`). |
| Notify | System | Admins are alerted. |
| Fulfil | Admin | Upload the document. Optionally push it into the Knowledge Base at the same time. The partner is notified. |
| Decline | Admin | Requires a written reason. The partner is notified. |

Only a `pending` request can be actioned (`ALREADY_PROCESSED`).

**Visibility.** Partners see only the requests they personally raised. Opening a
single request by ID applies the channel-manager scope, so an admin gets a 403 for
a request outside the companies they manage. The *list* page, however, is not
company-scoped for admins — every admin sees every pending request, and any admin
may fulfil or decline any of them. Treat the document-request queue as a shared
Extravis-wide inbox rather than a per-channel-manager one. **Sales reps have no
access to the module at all.**

---

## 13. Knowledge Base

A searchable library of published collateral.

- **Read and download:** every authenticated user, all four roles.
- **Publish, edit, delete:** admins.

Documents carry a title, category, description, and file, and are versioned — a
new version links back to the one it replaced. Every download is logged (which
also ticks the partner's onboarding checklist). Downloads use the same 30-minute
signed-link mechanism as opportunity attachments.

---

## 14. Training (LMS) and Certificates

Courses are authored by **admins**; enrolment and study are for **partners**.
Other roles can browse the catalogue.

### 14.1 Course lifecycle

A course is `draft` until an admin publishes it. Only `published` courses appear to
non-admins and only published courses can be enrolled in.

A course carries modules, an optional assessment (a set of scored questions), and a
passing score defaulting to **70%**.

### 14.2 Partner journey

```
  Enrol ──► ENROLLED ──► (open modules) ──► IN_PROGRESS ──► COMPLETED
                                                                │
                                        assessment passed, or all modules done
                                                                │
                                                    certificate auto-issued
```

- **Enrol.** One enrolment per course per user (`ALREADY_ENROLLED`).
- **Progress.** Ticking modules moves the enrolment to In Progress; completing
  every module completes it.
- **Assessment.** Submitting answers scores the attempt and increments the attempt
  count. Scoring at or above the passing score completes the course.
- **Certificate.** On completion the certificate PDF is **generated
  automatically** — no request, no admin approval, no manual upload. Generation is
  idempotent, and completing a course also re-evaluates the company's tier.

A legacy *request certificate → admin issues certificate* path still exists in the
API for enrolments completed before auto-issue, but the normal flow no longer uses
it.

---

## 15. Dashboards and Analytics

Each role lands on a different dashboard.

### 15.1 Partner dashboard

Own-submission counts by status (total, approved, rejected, pending, drafts), own
total and approved pipeline value, company tier with a progress bar toward the next
tier, LMS enrolled vs completed, pending document requests, the onboarding
checklist, and a timeline of recent activity.

### 15.2 Sales-rep dashboard

Scoped entirely to assigned opportunities: running / successful / unsuccessful POC
counts, overdue POCs, POC success rate, devices deployed, pipeline value currently
in POC, a personal POC stage funnel, and the rep's opportunity list.

### 15.3 Admin dashboard

Portal-wide (or channel-manager-scoped) KPIs: companies, partners, opportunities
by status, total and approved pipeline worth, overdue opportunities, pending
document requests. Plus:

- **Opportunity breakdown** by status
- **Monthly data** — submitted / approved / rejected per month
- **Analytics** — regions, tier distribution, industries, top companies, conversion
  funnel, recent activity feed
- **Target Plan analytics** — pipeline sliced by product, industry, stage, quarter,
  and Extravis sales rep, with **weighted pipeline** (Σ worth × probability)
- **City funnel** — value by city and quarter, parsed from the Time Frame field.
  Rows with an unparseable time frame group under "Unspecified" rather than
  vanishing from the totals.
- **Channel-manager dashboard** — the managed-companies view

---

## 16. Notifications

Notifications appear in the in-app bell (with an unread count) and, for most types,
are also emailed.

| Event type | Goes to |
|---|---|
| `opportunity_submitted` | All admins |
| `opportunity_approved` / `opportunity_rejected` / `opportunity_removed` | The submitting partner |
| `preferred_partner_tag` | The submitting partner |
| `internal_note_added` | The submitting partner (the note text itself stays hidden) |
| `multi_partner_conflict` | All admins |
| `deal_registered` | All admins |
| `deal_approved` / `deal_rejected` | The registering partner |
| `commission_approved` / `commission_paid` / `commission_void` | The commission recipient (in-app only) |
| `document_requested` | All admins |
| `document_request_fulfilled` / `document_request_declined` | The requesting partner |
| `certificate_requested` | Admins |
| `certificate_issued` | The partner |
| `channel_manager_assigned` | The assigned channel manager |

Users can mark individual notifications read, or clear the lot with Mark All Read.

---

## 17. Bulk Import

**Superadmin only.** Two importers, both driven by `.xlsx` uploads with a
downloadable blank template.

### 17.1 Opportunity import (2027 Target Plan workbook)

Expected columns, in order:

`S.No · Customer · Partner · Extravis Team · City · Country · Industry · Progress ·
Product · Price · Time Frame`

Behaviour:

- **Partner** creates the partner company if it does not exist.
- **Extravis Team** maps to a sales rep, creating the account if needed.
- Any account created as a side effect is `pending_activation` with a random
  password and an activation token — never immediately loginable.
- **Progress** (0.1–1.0) sets both the stage probability and the initial workflow
  status (mapping in §5).
- **Time Frame** (`Q3 - 2027`) is parsed into a quarter-end closing date; anything
  unparseable defaults to 31 December 2027.
- **Country** maps to a region.

### 17.2 Company import

The same pattern for partner-company records.

### 17.3 Limits

Uploads are size-capped at **20 MB**, verified to be genuine `.xlsx` files, and
limited to **5,000 data rows per file** (`TOO_MANY_ROWS`). Wrong or reordered
headers are refused with `INVALID_HEADERS` rather than silently mis-imported.

---

## 18. Exports

Any list you can see, you can export as **PDF** or **Excel**:

| Export | Available to |
|---|---|
| Opportunities | All roles, scoped to what they can see |
| Deals | Admins and partners — sales reps are refused |
| Companies | Admins |
| POCs | All roles, scoped |
| Licences | All roles, scoped |

Exports honour the filters active on screen (status, country, region, search) and
apply exactly the same scoping as the list itself — a partner exports their own
submissions, a channel manager their companies, a sales rep their assigned
opportunities. Every export is capped at **5,000 rows**.

---

## 19. AI Assistance

AI features are optional. If no API key is configured they are simply absent, and
nothing else in the portal changes. Every AI call degrades gracefully — a failure
is logged and the user-facing operation continues.

| Feature | Who | What it does |
|---|---|---|
| **Opportunity scoring** | Automatic on submit | Assigns a 0–100 quality score with a short written rationale, shown as a badge on the record. Runs in the background; the submit does not wait. |
| **Duplicate detection** | Automatic on submit | Flags likely duplicates the rule-based layers missed and links the records. Confidence must be ≥ 0.6. Adds the record to the Duplicate Review queue as flagged by `ai`. |
| **Summarise opportunity** | Admins | A 3–5 bullet summary of the customer context, scope, requirements, timing, and risks. Cached for 24 hours. Rate-limited to 20/minute. |
| **Rescore** | Admins | Re-runs the score on demand. Rate-limited to 20/minute. |
| **Knowledge Base Q&A** | All users | Ask a plain-language question; answers are drawn from indexed KB documents and cite the sources used. Rate-limited to 10/minute. |

Obvious personal data — email addresses and phone numbers — is scrubbed out of
payloads before they leave the portal.

---

## 20. Audit Logs

**Superadmin only.**

Every mutation writes an audit entry: the acting user, the action (`CREATE`,
`UPDATE`, `DELETE`, `START`, `CLOSE`, `REOPEN`, `STAGE_UPDATE`), the entity type
and ID, a before/after payload, and request metadata. Status transitions record
both the old and new value, so "who approved this and when" is always answerable.

The log is filterable by user, action, entity type, and date range.

---

## 21. Reference — Permission Matrix

✅ full · 🔵 scoped to what they own or manage · 👁 read-only · — no access

### Opportunities

| Action | Superadmin | Channel Mgr | Partner | Sales Rep |
|---|:--:|:--:|:--:|:--:|
| Create | — | — | ✅ | — |
| List / view | ✅ | 🔵 | 🔵 own | 🔵 assigned |
| Edit | — | — | 🔵 own, unlocked states | — |
| Submit | — | — | 🔵 own | — |
| Mark under review | ✅ | 🔵 | — | — |
| Approve / Reject | ✅ | 🔵 | — | — |
| Remove | ✅ | 🔵 | — | — |
| Internal notes | ✅ | 🔵 | — | — |
| Duplicate review queue | ✅ | 🔵 | — | — |
| Upload attachment | ✅ | ✅ | 🔵 own | 🔵 assigned |

### POC and Licences

| Action | Superadmin | Channel Mgr | Partner | Sales Rep |
|---|:--:|:--:|:--:|:--:|
| View POC | ✅ | 🔵 | 👁 own | 🔵 assigned |
| Start / edit / tick stages | ✅ | 🔵 | — | 🔵 assigned |
| Close / reopen POC | ✅ | 🔵 | — | 🔵 assigned |
| View licence | ✅ | 🔵 | 👁 own | 🔵 assigned |
| Create / edit licence | ✅ | 🔵 | — | 🔵 assigned |
| Deployment analytics page | ✅ | 🔵 | — | 🔵 |

### Deals, Commissions, Tiers

| Action | Superadmin | Channel Mgr | Partner | Sales Rep |
|---|:--:|:--:|:--:|:--:|
| Register a deal | — | — | ✅ | — |
| Approve / reject a deal | ✅ | ✅ | — | — |
| View commissions | ✅ | 🔵 | 🔵 own | — |
| Change commission status | ✅ | ✅ | — | — |
| Statements | ✅ | 🔵 | 🔵 own | — |
| Scorecard | — | — | ✅ | — |
| Leaderboard | ✅ | ✅ | ✅ | — |

### Administration

| Action | Superadmin | Channel Mgr | Partner | Sales Rep |
|---|:--:|:--:|:--:|:--:|
| Create company | ✅ | — | — | — |
| Edit company | ✅ | 🔵 | — | — |
| Delete company | ✅ | — | — | — |
| Create partner account | ✅ | 🔵 | — | — |
| Create admin / sales-rep account | ✅ | — | — | — |
| Edit / deactivate a user | ✅ | 🔵 non-admin users only | — | — |
| Users page | ✅ | — | — | — |
| Audit logs | ✅ | — | — | — |
| Bulk import | ✅ | — | — | — |

### Content and Activity

| Action | Superadmin | Channel Mgr | Partner | Sales Rep |
|---|:--:|:--:|:--:|:--:|
| Knowledge Base — read | ✅ | ✅ | ✅ | ✅ |
| Knowledge Base — publish / edit | ✅ | ✅ | — | — |
| Courses — create / edit | ✅ | ✅ | — | — |
| Courses — enrol and study | — | — | ✅ | — |
| Document request — raise | — | — | ✅ | — |
| Document request — fulfil / decline | ✅ | 🔵 | — | — |
| Activity log — create own | — | — | — | ✅ |
| Activity log — read a rep's month | ✅ | ✅ | — | 🔵 own |
| Activity log — edit / delete others' | ✅ | — | — | — |

---

## 22. Reference — Error Codes

### Authentication and accounts

| Code | Meaning |
|---|---|
| `INVALID_CREDENTIALS` | Wrong email or password (deliberately indistinguishable) |
| `ACCOUNT_LOCKED` | Five failed attempts; locked for 30 minutes |
| `ACCOUNT_NOT_ACTIVATED` | Activation link not yet used |
| `ACCOUNT_INACTIVE` | Account deactivated by an admin |
| `INVALID_ACTIVATION_TOKEN` | Activation link expired (72 h) or already used |
| `INVALID_RESET_TOKEN` | Password-reset link expired (1 h) or already used |
| `INVALID_CURRENT_PASSWORD` | Wrong current password on change-password |
| `TOKEN_REVOKED` / `REFRESH_TOKEN_REVOKED` | Session was logged out |
| `EMAIL_EXISTS` | An account already uses that email |

### Opportunities

| Code | Meaning |
|---|---|
| `DUPLICATE_BLOCKED` | Another partner holds exclusivity or ownership on this customer |
| `OPPORTUNITY_LOCKED` | An admin is reviewing it; editing is blocked |
| `CANNOT_EDIT` | Not in an editable status |
| `CANNOT_SUBMIT` | Only Draft or Rejected can be submitted |
| `CANNOT_REVIEW` | Only Pending can be marked under review |
| `CANNOT_APPROVE` / `CANNOT_REJECT` | Not in a reviewable status |
| `MAX_DOCUMENTS_REACHED` | Five attachments already |
| `CANNOT_DELETE_DOCUMENT` | Partners may only remove attachments while pending or under review |
| `FILE_TOO_LARGE` / `INVALID_FILE_TYPE` / `EMPTY_FILE` | Upload rejected |
| `INVALID_DOWNLOAD_TOKEN` | The 30-minute signed link expired |

### POC and licences

| Code | Meaning |
|---|---|
| `POC_ALREADY_STARTED` | This opportunity's POC already has a VM allocation |
| `POC_NOT_STARTED` | Cannot close a POC that never started |
| `POC_ALREADY_CLOSED` / `POC_CLOSED` | Reopen it before editing |
| `POC_NOT_CLOSED` | Cannot reopen an open POC |
| `STAGE_BEFORE_START` | A stage cannot complete before the POC began |
| `UNKNOWN_STAGE` | Stage key not one of the five |
| `INVALID_DATE_RANGE` | End before start, or expiry before activation |

### Deals, commissions, activities

| Code | Meaning |
|---|---|
| `EXCLUSIVITY_CONFLICT` | Another partner holds live exclusivity on this customer |
| `DEAL_NOT_PENDING` | Only pending deals can be approved or rejected |
| `INVALID_TRANSITION` | Not a legal commission status move |
| `INVALID_ACTIVITY_DATE` | Weekend, or a future date |
| `INVALID_OPPORTUNITY` | The linked opportunity does not exist |
| `INVALID_MONTH` | Month must be `YYYY-MM` |

### Training and content

| Code | Meaning |
|---|---|
| `ALREADY_ENROLLED` | One enrolment per course per user |
| `COURSE_NOT_COMPLETED` | Certificate requires completion |
| `NO_ASSESSMENT` | The course has no assessment configured |
| `ALREADY_PROCESSED` | The document request was already fulfilled or declined |
| `NO_COMPANY` | The partner account is not attached to a company |

### Import

| Code | Meaning |
|---|---|
| `INVALID_HEADERS` | Column names or order do not match the template |
| `TOO_MANY_ROWS` | Sheet exceeds the per-file row cap |
| `INVALID_FILE` | Not a real `.xlsx` file |

---

## 23. Behaviour Notes and Known Quirks

Things that surprise people. None are faults in the sense of broken code, but all
are worth knowing before you raise a ticket.

**23.1 Two different tier thresholds.** The tier *progress bar* on the partner
dashboard and scorecard is calculated from more generous thresholds (Gold at 5
approved opportunities, Platinum at 10; the scorecard uses approved *deal* counts
of 5 and 15) than the engine that performs the actual upgrade (Gold at 10 approved
opportunities **and** 50% LMS completion; Platinum at 20 **and** 80%). A partner
can therefore see a full progress bar while remaining on their current tier. The
authoritative rule is the one in §10.4.

**23.2 Opening a record changes it.** An admin merely *viewing* a `pending_review`
opportunity moves it to `under_review` and locks the partner out of editing. There
is no read-only peek.

**23.3 A finished POC is not a closed POC.** All five stages green still shows
Running until a human closes it with an outcome. Success rates count only closed
POCs.

**23.4 Licence status drifts on its own.** No one edits a record for it to go from
Active to Expiring Soon to Expired — the dates do that. Filtering by status always
reflects today, not the day the row was saved.

**23.5 Stage probability is manual.** Closing a POC successfully does not advance
the opportunity to 0.6, and recording a PO does not advance it to 0.9. If the
weighted-pipeline numbers look stale, it is usually because stages were never
updated.

**23.6 Sales reps are firewalled from the commercial modules.** Commissions,
scorecards, leaderboard, deal registration, and document requests all refuse sales
reps outright. This is deliberate: those modules predate the role and branch on
"partner or else everyone", so a sales rep reaching them would read the entire
dataset.

**23.7 A channel manager who manages no companies sees nothing.** Empty lists
everywhere, not everything. Assign companies to fix it.

**23.8 Partners are scoped to themselves, not their company.** Two partner users
at the same company do not see each other's opportunities in the opportunity list,
although POC and licence lists are scoped by company.

**23.9 Download links expire.** Signed file URLs last 30 minutes. A link copied
into a chat or a ticket will be dead by the time someone clicks it — send the
portal link instead.

**23.10 The document-request queue is not channel-scoped.** Unlike every other
admin list, the document-request list shows all admins every request, and any
admin can fulfil or decline any of them (see §12). Only the single-request view
applies the managed-companies check.

---

*Proprietary — © Extravis. All rights reserved.*
