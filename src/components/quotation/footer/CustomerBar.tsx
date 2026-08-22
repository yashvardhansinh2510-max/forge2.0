// Horizontal customer picker chip row.
import { Pressable, ScrollView, StyleSheet, Text } from "react-native";

import { colors } from "@/src/theme/tokens";
import { color as ds } from "@/src/design/tokens";
import { useBuilder } from "../context/BuilderContext";

export function CustomerBar() {
  const b = useBuilder();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 2 }}>
      {b.customers.map((c) => {
        const on = b.s.customerId === c.id;
        return (
          <Pressable
            key={c.id}
            testID={`cust-${c.id}`}
            onPress={() => b.setCustomer(c.id)}
            style={[styles.chip, on && styles.chipActive]}
          >
            <Text style={{ fontSize: 12, fontWeight: "600", color: on ? ds.brassDeep : colors.onSurface }}>
              {c.company || c.name}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  chipActive: { backgroundColor: ds.brassTint, borderColor: ds.brassLine },
});
