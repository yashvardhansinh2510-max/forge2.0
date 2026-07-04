// Lightweight toast — non-blocking success/error feedback.
// Mount <ToastHost /> once at the app root. Trigger via `toast.show(...)`.
import { Feather } from "@expo/vector-icons";
import { useEffect, useRef, useState } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, radius, spacing } from "@/src/theme/tokens";

type ToastKind = "success" | "error" | "info";
type ToastEvent = { kind: ToastKind; text: string };

let listeners: ((ev: ToastEvent) => void)[] = [];

export const toast = {
  show(text: string, kind: ToastKind = "info") {
    listeners.forEach((l) => l({ text, kind }));
  },
  success(text: string) { this.show(text, "success"); },
  error(text: string) { this.show(text, "error"); },
};

export function ToastHost() {
  const [ev, setEv] = useState<ToastEvent | null>(null);
  const opacity = useRef(new Animated.Value(0)).current;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const l = (e: ToastEvent) => {
      setEv(e);
      Animated.timing(opacity, { toValue: 1, duration: 180, useNativeDriver: true }).start();
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        Animated.timing(opacity, { toValue: 0, duration: 220, useNativeDriver: true }).start(({ finished }) => {
          if (finished) setEv(null);
        });
      }, 2400);
    };
    listeners.push(l);
    return () => { listeners = listeners.filter((x) => x !== l); };
  }, [opacity]);

  if (!ev) return null;
  const bg = ev.kind === "success" ? colors.success : ev.kind === "error" ? colors.error : colors.brand;
  const icon = ev.kind === "success" ? "check-circle" : ev.kind === "error" ? "alert-circle" : "info";

  return (
    <SafeAreaView pointerEvents="none" edges={["top"]} style={styles.host}>
      <Animated.View style={[styles.toast, { backgroundColor: bg, opacity }]}>
        <Feather name={icon as any} size={16} color="#fff" />
        <Text style={styles.text} numberOfLines={2}>{ev.text}</Text>
      </Animated.View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  host: { position: "absolute", top: 0, left: 0, right: 0, alignItems: "center", zIndex: 9999 },
  toast: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingHorizontal: spacing.lg, paddingVertical: 12, borderRadius: radius.pill,
    marginTop: 8, maxWidth: 480,
    shadowColor: "#000", shadowOpacity: 0.2, shadowOffset: { width: 0, height: 6 }, shadowRadius: 16, elevation: 6,
  },
  text: { color: "#fff", fontSize: 13, fontWeight: "600", flexShrink: 1 },
});
