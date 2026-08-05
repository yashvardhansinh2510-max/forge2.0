# Sanitary Bathroom Media & Quotation Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize Sanitary Bathroom product-media presentation across the existing editor/catalog/PDF workflow, enlarge quotation imagery responsively, persist desktop sidebar collapse, and remove PDF rotation/distortion regressions.

**Architecture:** Keep `ProductImage`, `productImageList`, Supabase Storage, `product_media`, and ReportLab as the existing system boundaries. Introduce pure fit/normalization helpers that both React Native and ReportLab consume conceptually, pass measured layout width into quotation grid decisions, and persist only shell UI preference in existing local storage.

**Tech Stack:** Expo 54, React Native Web, TypeScript, `expo-image`, React Native `FlatList`, AsyncStorage-backed storage utility, FastAPI/Python, ReportLab, Pillow, pytest.

## Global Constraints

- Reuse existing Product model, Product media collection, Supabase Storage, MongoDB, PDF renderer, Quotation Builder, image service, and caching layer.
- Do not create parallel image systems or duplicate images.
- Do not modify historical quotations or manually adjust existing catalog products.
- Preserve aspect ratio, never stretch/squash/crop important product parts, center automatically, and apply equal internal padding.
- Desktop-only sidebar collapse; mobile behavior remains the existing bottom bar.
- Do not hardcode image sizes; use design tokens and measured responsive breakpoints.
- Keep frontend and PDF image rendering orientation-neutral and visually consistent.

## Files and boundaries

- `frontend/src/components/quotation/helpers/media.ts`: canonical candidate ordering and shared media presentation metadata.
- `frontend/src/components/ProductImage.tsx`: one UI renderer; default normalized contain behavior, caching, fallback, and explicit intentional-crop opt-in.
- `frontend/src/components/quotation/helpers/responsive.ts`: pure measured-width quotation-column policy.
- `frontend/src/components/quotation/catalog/ProductExplorer.tsx`: pass the explorer pane width into the policy and use normalized card frames.
- `frontend/src/components/quotation/catalog/PickerCard.tsx`, `frontend/src/components/quotation/canvas/LineRow.tsx`, `frontend/src/components/quotation/sheets/ProductModal.tsx`, `frontend/src/components/quotation/sheets/SwapSheet.tsx`: remove inconsistent local image frames and consume the shared frame contract.
- `frontend/src/components/quotation/layout/BuilderShell.tsx`: measured pane width wiring and persistent quotation brand-rail preference.
- `frontend/app/(admin)/_layout.tsx`: persisted desktop admin sidebar collapse and animated shell width.
- `backend/pdf_generator.py`: remove forced rotation and implement orientation-preserving contain-fit placement.
- `backend/tests/unit/test_pdf_generator_media.py`: focused PDF/media regression tests.
- `frontend` lint/type checks and existing backend unit suite: regression gates.

### Task 1: Add failing pure media-fit tests

**Files:**
- Create: `backend/tests/unit/test_pdf_generator_media.py`
- Modify: `backend/pdf_generator.py` only after the tests fail

**Interfaces:**
- The tests will define the expected behavior for `contain_box(source_width, source_height, box_width, box_height, inset)` and `_landscape_bytes` removal/replacement.

- [ ] **Step 1: Write the failing tests**

```python
def test_contain_box_preserves_portrait_orientation_and_centers_it():
    box = contain_box(600, 1200, 180, 90, 6)
    assert box.width == 39
    assert box.height == 78
    assert box.x == 76.5
    assert box.y == 6

def test_pdf_image_bytes_do_not_rotate_portrait_sources():
    source = make_png(width=60, height=120, color="red")
    assert image_dimensions(_prepare_image_bytes(source)) == (60, 120)
```

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run: `cd forge2.0/backend && .venv/bin/pytest tests/unit/test_pdf_generator_media.py -q`

Expected: FAIL because the fit helper and orientation-neutral preparation function do not exist, and the current code rotates portrait images.

### Task 2: Implement orientation-neutral shared PDF geometry

**Files:**
- Modify: `backend/pdf_generator.py`
- Test: `backend/tests/unit/test_pdf_generator_media.py`

**Interfaces:**
- Produce `contain_box(source_width: float, source_height: float, box_width: float, box_height: float, inset: float = 0) -> tuple[float, float, float, float]`.
- Produce `_prepare_image_bytes(data: bytes) -> bytes` that preserves pixel orientation while allowing safe decode/encode normalization.

- [ ] **Step 1: Implement the smallest geometry and byte-preparation helpers**

Remove `_landscape_bytes()` and any call to it. Use decoded pixel dimensions to compute a centered, inset contain box. Do not apply a rotate, transpose, canvas transform, or aspect-ratio distortion.

- [ ] **Step 2: Update `_img()` to use the helper**

Fetch bytes through the existing `_remote_image_bytes` cache, inspect native dimensions, compute the contain box inside the current PDF cell, and create the ReportLab image at the computed dimensions. Keep the existing placeholder fallback.

- [ ] **Step 3: Run focused tests and existing PDF unit tests**

Run: `cd forge2.0/backend && .venv/bin/pytest tests/unit/test_pdf_generator_media.py tests/unit/test_pdf_chalan.py tests/unit/test_pdf_tile_chalan.py -q`

Expected: PASS with no portrait rotation regression.

### Task 3: Normalize the shared React Native image renderer

**Files:**
- Modify: `frontend/src/components/ProductImage.tsx`
- Modify: `frontend/src/components/quotation/helpers/media.ts`

**Interfaces:**
- Produce a shared `ProductImageFrame` contract with `contentFit`, `aspectRatio`, and uniform `inset` values consumed by quotation callers.
- Keep `productImageList()` and `resolveVariantImages()` as the only candidate-ordering paths.

- [ ] **Step 1: Add a focused executable regression check for the pure candidate/frame helpers**

Because the frontend has no test runner, add a small TypeScript-safe helper test module under `frontend/src/components/quotation/helpers/__tests__/media.test.ts` and run it through the repository's available TypeScript/lint validation. The test must assert that hero URL wins, gallery/images deduplicate, and frame policy is contain/centered with equal inset.

- [ ] **Step 2: Run the check before implementation**

Run: `cd forge2.0/frontend && npx tsc --noEmit`

Expected: FAIL on the new frame contract until it is implemented.

- [ ] **Step 3: Implement the normalized default**

Change `ProductImage` default behavior from `cover` to normalized `contain`; keep an explicit `contentFit="cover"` escape hatch for callers that intentionally crop. Apply a stable aspect-ratio frame, uniform inset, `overflow: hidden`, and the existing memory/disk cache and fallback behavior. Do not alter candidate source URLs or enlarge low-resolution bytes.

- [ ] **Step 4: Run frontend lint and TypeScript checks**

Run: `cd forge2.0/frontend && npx tsc --noEmit && npm run lint`

Expected: PASS, with no new warnings/errors from the renderer changes.

### Task 4: Fix quotation layout and all quotation image callers

**Files:**
- Modify: `frontend/src/components/quotation/helpers/responsive.ts`
- Modify: `frontend/src/components/quotation/catalog/ProductExplorer.tsx`
- Modify: `frontend/src/components/quotation/catalog/PickerCard.tsx`
- Modify: `frontend/src/components/quotation/canvas/LineRow.tsx`
- Modify: `frontend/src/components/quotation/sheets/ProductModal.tsx`
- Modify: `frontend/src/components/quotation/sheets/SwapSheet.tsx`

**Interfaces:**
- `quotationGridColumns(containerWidth: number): 1 | 2` is based on the measured explorer/picker container, not global window width.

- [ ] **Step 1: Add the failing responsive assertions**

Assert: `quotationGridColumns(640) === 1`, `quotationGridColumns(820) === 2`, `quotationGridColumns(1040) === 2`, and no result exceeds two columns. This encodes the required larger desktop cards and prevents the former three-column desktop behavior.

- [ ] **Step 2: Run the focused check and confirm failure against the current three-column policy**

Run: `cd forge2.0/frontend && npx tsc --noEmit`

Expected: the new assertions/policy are not satisfied by the current implementation.

- [ ] **Step 3: Implement measured-width layout**

Use `onLayout` or the existing measured shell width to feed the explorer grid. Keep the product picker sheet responsive and avoid window-width disagreement. Replace local fixed image dimensions where they conflict with the shared normalized frame; preserve readability, price/action hit targets, and virtualized list behavior.

- [ ] **Step 4: Run frontend checks**

Run: `cd forge2.0/frontend && npx tsc --noEmit && npm run lint`

Expected: PASS.

### Task 5: Persist desktop sidebar and quotation rail collapse

**Files:**
- Modify: `frontend/app/(admin)/_layout.tsx`
- Modify: `frontend/src/components/quotation/layout/BuilderShell.tsx`
- Modify: `frontend/src/utils/storage.ts` only if the existing API cannot support the preference

**Interfaces:**
- Persist keys: `forge.admin.sidebar.collapsed.v1` and `forge.builder.brandRail.collapsed.v1`.
- Phone bar and tablet icon rail remain unchanged.

- [ ] **Step 1: Add a failing state/markup check**

Assert that desktop renders an accessible collapse/expand button, collapsed mode uses the design rail width, and preference restoration reads the persisted boolean.

- [ ] **Step 2: Run the check before implementation**

Run: `cd forge2.0/frontend && npx tsc --noEmit`

Expected: FAIL until the state and accessible controls are present.

- [ ] **Step 3: Implement persisted collapse**

Load the existing storage value on mount, render desktop sidebar width from expanded/collapsed state using `layout.sidebar` and `layout.rail`, animate the web width transition, and add test IDs/accessibility labels. Persist changes without blocking navigation. Keep phone/tablet branches behaviorally identical.

- [ ] **Step 4: Implement persisted quotation brand rail state**

Load/save the existing builder rail collapse state and retain its current compact/tablet behavior. Do not couple it to the admin shell sidebar state.

- [ ] **Step 5: Run frontend checks**

Run: `cd forge2.0/frontend && npx tsc --noEmit && npm run lint`

Expected: PASS.

### Task 6: Run cross-system verification and inspect visual evidence

**Files:**
- Modify: only files required by verification findings; do not touch unrelated tile worktree changes.
- Evidence: `docs/superpowers/verification/2026-08-05-sanitary-bathroom-media-quotation-stabilization.md`

- [ ] **Step 1: Run the backend unit suite**

Run: `cd forge2.0/backend && .venv/bin/pytest tests/unit -q`

Expected: all existing unit tests plus the new media tests pass.

- [ ] **Step 2: Run frontend static checks**

Run: `cd forge2.0/frontend && npx tsc --noEmit && npm run lint`

Expected: exit 0 with no new app errors.

- [ ] **Step 3: Verify the PDF artifact**

Generate a quotation PDF through the existing route/test fixture, inspect its `%PDF` output and render at least one portrait source and one landscape source. Confirm no 90-degree rotation, stretch, crop, or unexpected flip.

- [ ] **Step 4: Verify responsive dimensions**

Exercise 1280, 1440, 1920, 768, 1024, 375, 390, and 430 widths. Check no horizontal overflow, sidebar overlap, clipped card content, or inconsistent image padding. Cover tiles, taps, basins, showers, and accessories.

- [ ] **Step 5: Record evidence and remaining limitations**

Write exact commands, pass/fail output, screenshots/artifact paths, and any unavailable live Supabase/browser verification into the evidence document. Do not claim PDF/editor visual parity from code inspection alone.

## Self-review checklist

- [ ] Every workstream maps to a task: media audit/root cause (Tasks 1–3), universal standard/padding/consistency (Task 3), responsive layout/performance (Task 4), sidebar (Task 5), PDF orientation/parity (Task 2), regression verification (Task 6).
- [ ] No schema, product-record, or parallel-storage changes are proposed.
- [ ] No frontend test command is claimed unless it exists or is explicitly recorded as unavailable.
- [ ] All new pure geometry behavior has a failing test before implementation.
- [ ] Existing unrelated tile changes are excluded from the file scope.
