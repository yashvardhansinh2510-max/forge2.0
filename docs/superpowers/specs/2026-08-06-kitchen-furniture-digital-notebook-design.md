# Kitchen and Furniture digital notebook

Date: 2026-08-06
Status: design approved for written-spec review

## Goal

Rebuild the Kitchen/Furniture feature as a small, floor-isolated Indian office
notebook. The feature has exactly two floor modules: Kitchen Floor and
Furniture Floor. Each module has exactly two views: Follow-ups and Quotation
Follow-ups. The rest of the ERP remains outside this feature and is not
removed.

The existing prototype is not a foundation for new behavior. Its
`project_followups` write path, extra CRM fields, project stages, dashboards,
and modal-first UI are retired. Existing shared follow-up infrastructure is
reused instead.

## Decisions and invariants

### Scope and floors

- Kitchen Floor uses the existing `second-floor` identifier and displays
  `Kitchen Floor`.
- Furniture Floor uses the existing `third-floor` identifier and displays
  `Furniture Floor`.
- Existing unrelated ERP floors and modules remain available outside this
  feature, preserving the rest of the application.
- Every notebook query, write, customer lookup, timeline event, notification,
  and migration is scoped to the active feature floor.
- A Kitchen record must never be returned by a Furniture request, and the
  reverse must also hold.

### Customer identity

- A new row resolves the customer by normalized mobile number within the
  active floor.
- If there is a match, the row references that customer; no customer is
  duplicated.
- If there is no match, the existing customer service/path creates one once,
  and the row references the new customer.
- Customer identity is independent from notebook conversion. Conversion never
  creates another customer or another notebook row.
- There is at most one notebook row per customer per floor. The backend
  enforces this with a floor-scoped notebook identity and a unique index; an
  attempted duplicate resolves to the existing row.

### Follow-up fields

The notebook-facing Follow-up field allowlist is exactly:

- Customer Name
- Mobile Number
- Address
- Kitchen Type: GI or SS
- Referred By
- Architect / Interior Designer
- Status: New, Pending, Won, or Lost
- Notes

New Follow-up creation exposes the same fields except Status; new rows default
to New. No date, site visit, pipeline stage, budget, salesperson, task,
project, dashboard, CRM, or other invented field is exposed or accepted by
the notebook-specific write contract.

Customer Name, Mobile Number, and Kitchen Type are required. Address,
Referred By, Architect / Interior Designer, and Notes are optional. Mobile
numbers are normalized before matching and validation.

### Quotation Follow-up fields

A Quotation Follow-up can be created only by converting an existing Follow-up.
It keeps the original row ID, customer reference, all Follow-up fields, and
timeline. It adds exactly:

- Quotation Price
- Estimated Value
- Quotation Date

The conversion endpoint is idempotent. Repeating conversion returns the
existing converted row and cannot create a duplicate customer or quotation
follow-up.

### Lost rule

Lost is unavailable while Notes is empty or whitespace-only. The status patch
must be rejected server-side as well, so the rule cannot be bypassed by a
direct request. When a row becomes Lost, the existing activity/timeline
service records the saved lost note/reason, timestamp, and acting user. The
timeline event is the audit record; no additional Lost Reason field is added
to the notebook.

Won requires confirmation, records a Status changed/Won timeline event, locks
Follow-up fields from further editing, cannot transition back to New, and
continues to allow the three quotation fields to be updated after conversion.

## Backend architecture

The existing `followups` collection and follow-up service boundaries remain
the source of truth. The model gains only the optional notebook attributes
needed by the allowlist and conversion. Internal fields used by the shared
follow-up engine may remain in storage but are excluded from notebook
responses and cannot be edited through the notebook contract.

The implementation will:

1. Add a narrow notebook DTO/serializer and allowlisted create/update patch
   handling to the existing follow-up routes or a clearly named subrouter
   backed by the same collection and services.
2. Add floor-scoped customer resolution by normalized mobile, using existing
   customer and floor helpers.
3. Add a conversion operation that atomically marks the same follow-up as
   quotation-converted and stores the three quotation fields.
4. Route all notebook activity through existing activity/timeline,
   notification, permission, and audit helpers.
5. Retire the prototype `project-workspaces` route/model usage after data
   migration; do not add another collection or parallel service.

Every notebook mutation emits an immutable timeline event through the existing
timeline service. The event vocabulary is Created, Edited, Converted to
quotation, Quotation price updated, Status changed, Won, Lost, Lost note, and
Customer updated. Events are ordered newest first and are audit-only; they
cannot be edited or deleted from the notebook.

### Legacy migration

An idempotent migration maps existing `project_followups` records into the
unified follow-up representation. It resolves customers by floor and mobile,
maps only compatible fields, maps existing quotation amount/budget/date into
the three quotation attributes when the record is already converted, and
creates a migration timeline event. Unsupported prototype fields are not
exposed. The old collection is left untouched for recovery; the application
stops reading it after migration.

## Frontend architecture and behavior

The existing dynamic floor route may remain as the shared implementation for
the two floor modules, but it must render only the two specified views. The
sidebar keeps the two feature entries and removes feature-only prototype
destinations. No project journal, notebook journal, activity feed, executive
page, CRM screen, or additional dashboard is reachable from either module.

### Notebook grid

The primary surface is a dense, calm table styled like an Indian office diary:
large writing space, restrained typography, clear row lines, adjustable
columns on desktop, and no decorative dashboard KPI strip.

Each cell is independently editable. Selecting a cell changes only that cell
to an editor. Enter or blur submits a field-level patch; a saving indicator is
shown in that cell, errors restore the previous value, and the rest of the row
does not re-render into edit mode. Mobile and tablet use a horizontally
scrollable grid with touch-sized targets; no action relies on hover.

The grid columns are exactly the Follow-up allowlist. Quotation Follow-ups
append only the three quotation columns. A Quotation filter/view switch leads
to the Quotation Follow-ups view rather than introducing a third page.

Desktop columns are resizable, widths persist locally, the header is sticky,
and the Customer Name column is sticky while horizontally scrolling. Tablet
and phone use horizontal scrolling and never compress text to the point of
unreadability. Touch targets are at least 44px. There is no horizontal
clipping or hover-only action.

### Creation and conversion

Notebook editing is autosaved. There is no Save button anywhere. New
Follow-up is an inline full-width draft row on desktop/tablet and a bottom
sheet only on phone. It contains only the specified creation fields and is
created automatically once the required fields are valid; incomplete drafts
can be cancelled with Escape or the close affordance. Existing fields persist
immediately through the follow-up service on blur or Enter. Every edited cell
shows Saving, Saved, or Error without changing the rest of the row.

Conversion is an inline row action available on an unconverted Follow-up.
Internally it sets `is_converted = true` and stores `quotation_price`,
`estimated_value`, and `quotation_date` on the same record. The Follow-up view
automatically excludes converted rows and Quotation Follow-ups automatically
includes them. Once converted, the same row exposes the three quotation
fields and appears in the Quotation Follow-ups view.

Currency is displayed in Indian rupees. Quotation Price and Estimated Value
use ₹ formatting; Quotation Date uses dd/mm/yyyy.

### Concurrency and keyboard workflow

Every row carries its `updated_at` revision. A field patch includes the
revision observed by the client. If another employee has changed the row,
the server returns Conflict instead of silently overwriting it. The client
reloads the row and highlights the changed cells.

Keyboard behavior is part of the notebook contract: Enter commits the current
cell, Down moves to the next row, Tab moves to the next column, Shift+Tab moves
to the previous column, Escape cancels the edit, and arrow keys navigate cells.

### Filters

The only filter entries are All, Pending, Won, Lost, New, and Quotation.
Quotation selects the second view; the other entries filter the current
Follow-up view by the four allowed statuses. Search, if retained for usability,
is debounced, floor-scoped, and matches only Customer Name, Mobile Number,
Address, Architect / Interior Designer, Referred By, and Notes. It never
matches quotation fields.

### Appearance and scale

The visual direction is an Indian office register: calm, dense, minimal, and
legible. There are no KPI cards, dashboard widgets, kanban columns, charts,
CRM pipeline controls, or unnecessary whitespace.

When a view has no rows, it shows one notebook page with “No follow-ups yet.”
and the New Follow-up action. The list supports 10,000+ rows through
server-side pagination/incremental loading, debounced search, and virtualized
row rendering. It must not fetch the entire notebook into the browser.

## Error handling and security

- Server-side floor authorization is required on every endpoint.
- Notebook responses use an explicit allowlist so internal CRM/automation
  metadata cannot leak into the UI.
- Invalid status, Kitchen Type, quotation-only field, or cross-floor customer
  reference returns a validation error without partial writes.
- Lost status without non-empty Notes returns a validation error.
- Field-level update failures leave the cell at its last confirmed value.
- Conversion is safe to retry and never duplicates records.
- Each field patch carries `updated_at`; stale revisions return HTTP 409
  Conflict, never silently overwrite another employee, and cause the client
  to reload and highlight changed cells.
- Autosave state is restored from the server after reload.

## Testing and verification

Backend coverage will include:

- exact notebook create/update field allowlists;
- GI/SS and New/Pending/Won/Lost validation;
- customer reuse by floor/mobile and no duplicate creation;
- conversion inheritance, quotation-only fields, and idempotency;
- Lost rejection without Notes and timeline payload with note, date, and user;
- Kitchen/Furniture read and write isolation;
- legacy migration idempotency;
- optimistic-lock conflicts and changed-cell reload behavior;
- one-notebook-row-per-customer enforcement;
- Won confirmation, lock, and status-transition rules;
- pagination, search-field allowlisting, and quotation-field exclusion.

Frontend coverage will include:

- exact columns and filters;
- creation form field allowlist;
- single-cell patch behavior and rollback on error;
- disabled Lost action with empty Notes;
- conversion moving the same row to Quotation Follow-ups;
- autosave status indicators and reload persistence;
- conflict highlighting and keyboard navigation;
- virtualized pagination behavior and empty state;
- responsive rendering at phone, tablet, and desktop widths.

Verification also requires the existing backend unit suite, frontend
TypeScript/typecheck, frontend production build, responsive smoke checks, and
console-error checks. Existing unrelated tests and behavior must remain green.
The final production audit must also confirm no Save buttons, no duplicate
customers, no duplicate notebook rows, idempotent migration, a clean working
tree, and readiness for production.

## Explicit non-goals

- No new CRM pipeline or stage system.
- No site-visit fields or filters.
- No executive/dashboard/project-journal pages for this feature.
- No duplicate customer model or parallel notebook collection.
- No removal of unrelated ERP floors or modules.
