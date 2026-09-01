import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const scaffold = read("../src/components/mobile/AppScaffold.tsx");
assert.match(scaffold, /edges=\{\["top", "left", "right"\]\}/);
assert.match(scaffold, /edges=\{\["bottom"\]\}/);

const adminShell = read("../app/(admin)/_layout.tsx");
assert.match(adminShell, /if \(contextualNotebookTabs\)/);
assert.match(adminShell, /styles\.notebookPhoneBar/);
assert.match(adminShell, /bottom-nav-notebook-workspace/);
assert.doesNotMatch(adminShell, /bottom-fab-new-quotation[\s\S]{0,600}contextualNotebookTabs/);

const phoneSafeAreaRoutes = [
  "../app/(admin)/payments.tsx",
  "../app/(admin)/payments-list.tsx",
  "../app/(admin)/quotations/[id]/place-order.tsx",
  "../app/(admin)/customers/index.tsx",
  "../app/(admin)/customers/new.tsx",
  "../app/(admin)/customers/[id].tsx",
  "../app/(admin)/customers/[id]/edit.tsx",
  "../app/(admin)/walkins/index.tsx",
  "../app/(admin)/walkins/new.tsx",
  "../app/(admin)/walkins/[id].tsx",
  "../app/(admin)/purchase-orders/[id].tsx",
];
for (const path of phoneSafeAreaRoutes) {
  assert.match(read(path), /edges=\{isPhone \? \[\] : \["top"\]\}/, `${path} bypasses AppScaffold's phone top inset`);
}

const followups = read("../app/(admin)/followups.tsx");
assert.match(followups, /isPhone \? renderFollowupList\(true\)/);
assert.match(followups, /ListHeaderComponent=\{phone/);
assert.match(followups, /scrollEnabled=\{phone\}/);
assert.match(followups, /style=\{styles\.mobileDetailScroll\} contentContainerStyle=\{styles\.mobileDetailContent\}/);
assert.match(followups, /flexBasis: "48%"/);
assert.match(followups, /maxWidth: "48%"/);

const legacyBottomSheet = read("../src/components/BottomSheet.tsx");
assert.match(legacyBottomSheet, /import \{ Sheet \} from "@\/src\/design\/components"/);
assert.doesNotMatch(legacyBottomSheet, /\bModal\b/);

const tileMovementSheets = read("../src/components/tiles/TileMovementSheets.tsx");
assert.match(tileMovementSheets, /import \{ Sheet \} from "@\/src\/design\/components"/);
assert.doesNotMatch(tileMovementSheets, /\bModal\b/);
assert.match(tileMovementSheets, /footer=\{<SheetFooter/);
assert.match(tileMovementSheets, /accessibilityLabel=\{`Enter quantity for \$\{name\}`\}/);

const purchases = read("../app/(admin)/purchases.tsx");
assert.match(purchases, /import \{ Sheet \} from "@\/src\/design\/components"/);
assert.doesNotMatch(purchases, /\bModal\b/);
assert.match(purchases, /accessibilityRole="button"/);

const productImages = read("../src/components/catalog/ProductImageManager.tsx");
assert.match(productImages, /const \{ isPhone \} = useBp\(\)/);
assert.doesNotMatch(productImages, /winW >= 640/);

const tileTable = read("../src/components/tiles/TileTable.tsx");
assert.match(tileTable, /scrollOwner === "parent"/);
assert.match(tileTable, /const innerScroll = Boolean\(fillViewport\).*scrollOwner === "self"/);
assert.match(tileTable, /enabled=\{innerScroll\}/);
assert.match(tileTable, /data\.map\(renderMobileRow\)/);

const systemSettings = read("../app/(admin)/settings-system.tsx");
assert.match(systemSettings, /scroll=\{false\}/);
assert.match(systemSettings, /<ScrollView/);

console.log("mobile shell, sheet, safe-area, list ownership, and notebook navigation contracts: 30 assertions passed");
