import { useEffect, useState } from "react";
import { Text, View } from "react-native";

import { Button, PillTabs, TextField } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme/tokens";

import { customDateRange, inclusiveEndDay } from "./periodDates";
import { PERIOD_PRESETS, type SelectedPeriod } from "./useSalesPeriod";

export type FloorOption = { id: string; name: string };

/** Business-unit names the owner actually uses, rather than the floor slugs
 *  the database stores. Matches the mapping the Executive workspace already
 *  renders, so the two screens never label the same unit differently. */
export const FLOOR_LABEL: Record<string, string> = {
  "first-floor": "Sanitary",
  "ground-floor": "Tiles",
};

/**
 * Floor filter, date filter, and the custom range — requirements 10 and 11.
 *
 * Both filters are plain wrapping pill rows in the page body rather than in
 * the header's `right` slot: that slot's flex row does not wrap, and a
 * multi-option row pushed the page wider than a 375px viewport the last time
 * an analytics screen tried it.
 */
export function SalesFilters({
  floors, floorId, onFloorChange, period, onPeriodChange,
}: {
  floors: FloorOption[];
  floorId: string;
  onFloorChange: (id: string) => void;
  period: SelectedPeriod;
  onPeriodChange: (next: { preset: string; dateFrom?: string | null; dateTo?: string | null }) => void;
}) {
  const isCustom = period.preset === "custom";
  // Starts collapsed even when the active period IS custom: the smart default
  // resolves to a custom range whenever it falls back to the last month with
  // orders, and popping the date-entry form open on first load would present
  // a form the owner never asked for. The Custom pill still reads as
  // selected, with the resolved range named underneath it.
  const [showCustom, setShowCustom] = useState(false);
  const [from, setFrom] = useState((period.dateFrom || "").slice(0, 10));
  const [to, setTo] = useState(inclusiveEndDay(period.dateTo));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setFrom((period.dateFrom || "").slice(0, 10));
    setTo(inclusiveEndDay(period.dateTo));
  }, [period.dateFrom, period.dateTo]);

  const applyCustom = () => {
    const range = customDateRange(from.trim(), to.trim());
    if (!range) {
      setError("Enter valid dates as YYYY-MM-DD, with the end on or after the start.");
      return;
    }
    setError(null);
    setShowCustom(false);
    onPeriodChange({ preset: "custom", ...range });
  };

  return (
    <View style={{ gap: spacing.lg }} testID="sales-data-filters">
      <View style={{ gap: spacing.sm }}>
        <Text style={type.overline}>Business unit</Text>
        <PillTabs
          testID="sales-data-floor"
          value={floorId || "all"}
          onChange={onFloorChange}
          options={[
            { value: "all", label: "All units" },
            ...floors.map((f) => ({ value: f.id, label: FLOOR_LABEL[f.id] || f.name })),
          ]}
        />
      </View>

      <View style={{ gap: spacing.sm }}>
        <Text style={type.overline}>Period · UTC</Text>
        <PillTabs
          testID="sales-data-preset"
          value={showCustom || isCustom ? "custom" : period.preset}
          onChange={(value) => {
            if (value === "custom") {
              setShowCustom(true);
              return;
            }
            setShowCustom(false);
            setError(null);
            onPeriodChange({ preset: value });
          }}
          options={[
            ...PERIOD_PRESETS.map((p) => ({ value: p.value as string, label: p.label })),
            { value: "custom", label: "Custom" },
          ]}
        />
        {isCustom && !showCustom ? (
          <Text style={[type.caption, { color: colors.onSurfaceMuted }]}>
            Showing {period.label}
          </Text>
        ) : null}
      </View>

      {showCustom ? (
        <View style={{ gap: spacing.sm }} testID="sales-data-custom-range">
          <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
            <TextField
              label="From"
              value={from}
              onChangeText={setFrom}
              placeholder="2026-07-01"
              autoCapitalize="none"
              containerStyle={{ flex: 1, minWidth: 150 }}
            />
            <TextField
              label="To"
              value={to}
              onChangeText={setTo}
              placeholder="2026-07-31"
              autoCapitalize="none"
              containerStyle={{ flex: 1, minWidth: 150 }}
            />
          </View>
          {error ? <Text accessibilityRole="alert" style={[type.caption, { color: colors.error }]}>{error}</Text> : null}
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Button label="Apply range" icon="calendar" onPress={applyCustom} />
            <Button
              label="Cancel"
              variant="secondary"
              onPress={() => { setShowCustom(false); setError(null); }}
            />
          </View>
        </View>
      ) : null}
    </View>
  );
}
