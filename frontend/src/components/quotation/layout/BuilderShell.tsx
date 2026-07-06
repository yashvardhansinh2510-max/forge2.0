// BuilderShell V4
// -----------------------------------------------------------------------------
// Three-column workspace inspired by the Forge V4 mockup:
//   [Brand rail 240] · [Product Explorer flex] · [Quotation panel 460]
//
// Responsive strategy (measured on container width, not window):
//   * width >= 1180  → full V4 (BrandRail + Explorer + Quotation)
//   * width >= 820   → BrandRail + Quotation, Explorer opens as picker sheet
//   * else           → Mobile: Quotation only + FAB → picker sheet, product modal
// -----------------------------------------------------------------------------
import { useEffect, useState } from "react";
import { KeyboardAvoidingView, LayoutChangeEvent, Platform, StyleSheet, View } from "react-native";

import { colors } from "@/src/theme/tokens";

import { useBuilder } from "../context/BuilderContext";
import { BrandRail } from "../catalog/BrandRail";
import { ProductExplorer } from "../catalog/ProductExplorer";
import { QuotationPane } from "../panes/QuotationPane";
import { AssistantSheet } from "../sheets/AssistantSheet";
import { CustomProductSheet } from "../sheets/CustomProductSheet";
import { CustomerSwitcherSheet } from "../sheets/CustomerSwitcherSheet";
import { DescriptionSheet } from "../sheets/DescriptionSheet";
import { DiscountSheet } from "../sheets/DiscountSheet";
import { ProductModal } from "../sheets/ProductModal";
import { ProductPickerSheet } from "../sheets/ProductPickerSheet";
import { RoomSheet } from "../sheets/RoomSheet";
import { SwapSheet } from "../sheets/SwapSheet";
import { BuilderTopbar } from "./BuilderTopbar";
import { MobileSummaryBar } from "./MobileControls";

const THREE_PANE = 1180;
const TWO_PANE = 820;

export function BuilderShell({ onBack }: { onBack: () => void }) {
  const b = useBuilder();
  const [w, setW] = useState(0);

  const onLayout = (e: LayoutChangeEvent) => setW(e.nativeEvent.layout.width);

  const threePane = w >= THREE_PANE;
  const twoPane = !threePane && w >= TWO_PANE;
  const isPhone = !threePane && !twoPane;

  const railW = w >= 1400 ? 260 : 240;
  const quotationW = w >= 1440 ? 480 : w >= 1200 ? 440 : 400;

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
        <View style={{ flex: 1, backgroundColor: colors.surface }} />
      ) : threePane ? (
        <View style={{ flex: 1, flexDirection: "row", minHeight: 0, overflow: "hidden" }}>
          <View style={{ width: railW, overflow: "hidden" }}>
            <BrandRail />
          </View>
          <View style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: "hidden" }}>
            <ProductExplorer />
          </View>
          <View style={{ width: quotationW, minHeight: 0, overflow: "hidden", borderLeftWidth: StyleSheet.hairlineWidth, borderColor: colors.border }}>
            <QuotationPane />
          </View>
        </View>
      ) : twoPane ? (
        <View style={{ flex: 1, flexDirection: "row", minHeight: 0, overflow: "hidden" }}>
          <View style={{ width: 220, overflow: "hidden" }}>
            <BrandRail />
          </View>
          <View style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: "hidden" }}>
            <QuotationPane />
          </View>
        </View>
      ) : (
        <View style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
          <View style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
            <QuotationPane />
          </View>
          <MobileSummaryBar />
        </View>
      )}

      {/* Universal sheets */}
      <ProductModal />
      <CustomProductSheet />
      <CustomerSwitcherSheet />
      <DiscountSheet />
      <RoomSheet />
      <DescriptionSheet />
      <SwapSheet />

      {/* Mobile / tablet-only sheets */}
      {isPhone || twoPane ? <ProductPickerSheet /> : null}
      {(isPhone || twoPane) && !threePane ? <AssistantSheet /> : null}
    </KeyboardAvoidingView>
  );
}
