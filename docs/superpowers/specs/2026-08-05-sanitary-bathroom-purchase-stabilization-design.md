# Sanitary Bathroom Purchase Workflow Stabilization — Design

**Date:** 2026-08-05  
**Status:** Draft for user review  
**Scope:** Production-quality stabilization of the Sanitary Bathroom purchasing workflow

## Mission

Make the existing Sanitary Bathroom (`first-floor`) purchase workflow reliable for real customer use without creating duplicate models, services, layouts, or workflows. This is a stabilization pass, not a feature sprint.

## Approach

Use vertical stabilization slices:

1. Bulk movement and concurrency/error reporting.
2. Customer Purchase search, brand, and workflow-stage filtering.
3. Sanitary dispatch → Chalan → PDF → synchronized history/events.
4. Responsive UI, performance, and regression audit.

Each slice is verified before the next slice begins. Existing architecture remains authoritative.

## Architecture and data flow

`purchase_orders.items[]` and embedded `purchase_orders.chalans[]` remain the source of truth. No new purchase, dispatch, Chalan, or customer-history model is introduced.

Bulk movement continues to use the existing stage-change primitive and optimistic-concurrency guards. The bulk endpoint returns structured per-item results for success, conflict, validation, permission, and not-found outcomes. The operation is retry-safe and does not claim full success when any item fails.

Customer Purchases continues to use `/purchases/customers/{customer_id}/workspace`. Search, brand, and stage are one composable filter contract; counts are derived from the same item set as the visible purchase cards. Clearing a filter restores the complete history. The existing purchase-card/list layout is preserved.

Sanitary dispatch reuses the existing purchase-order and Chalan lifecycle plus `services/chalan_stage.py`. Parent purchase orders are always resolved through floor-scoped access. Existing activity, timeline, notification, and customer-history producers are reused exactly once per successful transition, with source identity and floor identity preserved for idempotency and isolation.

The existing `build_chalan_pdf` renderer is expanded to render customer name/address/phone, order number, dispatch date, product brand/name/size/finish/quantity/unit/rate/total, transport, remarks, company details, and receiver/sender signature areas. PDF generation remains on-demand through the existing download-token path.

## Failure handling

- Empty bulk selection is rejected before writes.
- Each bulk item is authorized and re-read at mutation time.
- Concurrent changes produce an item-level conflict rather than an overwrite.
- Successful items remain applied when other items fail; the client highlights failures and offers retry.
- Chalan over-release is rejected; concurrent release returns a conflict and requires refresh/retry.
- Partial dispatch and repeated dispatch are represented by existing embedded Chalan and stage state, not a parallel record.
- Missing customer/media/optional PDF data uses existing safe fallbacks and never crashes the workflow.
- Floor and role authorization remain enforced at every id-addressed read and write.

## UI behavior

The Customer Purchases layout is frozen. Only data filtering, filter controls, loading/error/empty states, selection feedback, and button hierarchy may change. Existing purchase cards and responsive shell are reused at desktop, tablet, and mobile widths.

Bulk actions show progress, disable duplicate submission while in flight, report partial success, and preserve selection for failed items. Filter state is explicit and removable; search combines with brand and stage rather than replacing them.

Chalan actions appear only where the current purchase lifecycle and permission allow them. Download and generation states are visible, and PDF failures are recoverable without losing the persisted dispatch state.

## Verification

Backend tests cover:

- bulk move sizes 1, 5, and 20;
- mixed suppliers and brands;
- partial moves, invalid quantities, permission failures, and optimistic-concurrency conflicts;
- combined search/brand/stage filters and large customer histories;
- single, multi-item, partial, complete, repeated, and concurrent Chalan/dispatch operations;
- PDF field presence, wrapping, totals, transport, remarks, signatures, branding, and safe fallbacks;
- exactly-once activity, timeline, notification, and customer-history outcomes;
- floor isolation and existing permission boundaries.

Frontend verification includes `npx tsc --noEmit`, available focused checks, and browser QA at desktop/tablet/mobile widths. Existing Ground Floor Tiles, Sanitary Bathroom, Purchase Orders, Payments, History, Notifications, Timeline, Floor Isolation, and Permissions regressions are rerun. The iOS simulator-browser workflow is used only if a runnable native iOS build and simulator are available; Expo deployment is limited to configuration/readiness checks unless separately authorized.

The final verification report records direct evidence and explicitly marks any live-storage, native-simulator, or deployment check that the environment cannot perform.

## Scope boundaries

In scope: the Sanitary Bathroom purchase workflow and directly adjacent shared producers, renderers, permissions, floor isolation, performance, and regression coverage.

Out of scope: new domain models/services, a Customer Purchases redesign, Sales Data / Executive OS, destructive production-data cleanup, and EAS/TestFlight/App Store/Play Store/hosting deployment.

## Definition of done

- Multi-product operations reliably complete or report item-level failures.
- Customer filters combine correctly and remain fast without a second layout.
- Sanitary Chalan generation and complete PDF output work through the existing workflow.
- Activity, timeline, notification, and customer history remain synchronized without duplicates.
- UI states are clear and responsive across supported layouts.
- Backend, frontend, floor isolation, permission, performance, PDF, and regression checks provide evidence for the milestone requirements.
