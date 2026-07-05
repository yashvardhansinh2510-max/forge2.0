// BuilderShell
// -----------------------------------------------------------------------------
// Responsive layout brain. Measures its OWN container (not the window) via
// onLayout so the sidebar-eating parent layout doesn't skew our breakpoint math.
//
//   * width >= 1180 → 3-pane (Catalog · Quotation · Assistant)
//   * width >= 820  → 2-pane (Catalog · Quotation) + Assistant sheet
//   * else          → Mobile: Quotation-only + FAB → picker sheet + Assistant sheet
// -----------------------------------------------------------------------------
import { useEffect, useState } from "react";
import { KeyboardAvoidingView, LayoutChangeEvent, Platform, StyleSheet, View } from "react-native";

import { colors } from "@/src/theme/tokens";

import { useBuilder } from "../context/BuilderContext";
import { CatalogPane } from "../catalog/CatalogPane";
import { AssistantPane } from "../panes/AssistantPane";
import { QuotationPane } from "../panes/QuotationPane";
import { AssistantSheet } from "../sheets/AssistantSheet";
import { DescriptionSheet } from "../sheets/DescriptionSheet";
import { DiscountSheet } from "../sheets/DiscountSheet";
import { ProductPickerSheet } from "../sheets/ProductPickerSheet";
import { RoomSheet } from "../sheets/RoomSheet";
import { SwapSheet } from "../sheets/SwapSheet";
import { BuilderTopbar } from "./BuilderTopbar";
import { MobileSummaryBar } from "./MobileControls";

// Layout thresholds tuned for real container width (not window). Tablet
// landscape must get the true 3-pane experience — the sidebar-eating parent
// leaves ~1000-1120px on iPad Pro landscape, so THREE_PANE starts at 980.
const THREE_PANE = 980;
const TWO_PANE = 720;

export function BuilderShell({ onBack }: { onBack: () => void }) {
  const b = useBuilder();
  const [w, setW] = useState(0);

  const onLayout = (e: LayoutChangeEvent) => setW(e.nativeEvent.layout.width);

  const threePane = w >= THREE_PANE;
  const twoPane = !threePane && w >= TWO_PANE;
  const isPhone = !threePane && !twoPane;

  // Catalog + assistant widths scale with available room.
  const catalogW = w >= 1400 ? 340 : w >= 1200 ? 300 : 270;
  const assistantW = w >= 1400 ? 380 : w >= 1200 ? 340 : 300;

  // On smaller layouts, when a line/product gets focused, open the Assistant sheet.
  useEffect(() => {
    if (threePane) return;
    if (b.assistantFocus) b.setAssistantOpenMobile(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [b.assistantFocus, threePane]);

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: colors.surface }}
      onLayout={onLayout}
    >
      <BuilderTopbar onBack={onBack} />

      {w === 0 ? (
        // Wait for measurement to avoid flashing the wrong layout.
        <View style={{ flex: 1, backgroundColor: colors.surface }} />
      ) : threePane ? (
        <View style={{ flex: 1, flexDirection: "row" }}>
          <View style={{ width: catalogW, borderRightWidth: StyleSheet.hairlineWidth, borderColor: colors.border }}>
            <CatalogPane />
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <QuotationPane />
          </View>
          <View style={{ width: assistantW }}>
            <AssistantPane />
          </View>
        </View>
      ) : twoPane ? (
        <View style={{ flex: 1, flexDirection: "row" }}>
          <View style={{ width: 300, borderRightWidth: StyleSheet.hairlineWidth, borderColor: colors.border }}>
            <CatalogPane />
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <QuotationPane />
          </View>
        </View>
      ) : (
        <View style={{ flex: 1 }}>
          <View style={{ flex: 1 }}>
            <QuotationPane />
          </View>
          <MobileSummaryBar />
        </View>
      )}

      {/* Universal sheets */}
      <DiscountSheet />
      <RoomSheet />
      <DescriptionSheet />
      <SwapSheet />

      {/* Mobile-only sheets */}
      {isPhone ? <ProductPickerSheet /> : null}
      {(isPhone || twoPane) && !threePane ? <AssistantSheet /> : null}
    </KeyboardAvoidingView>
  );
}
