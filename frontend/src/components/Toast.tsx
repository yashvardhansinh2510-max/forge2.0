// Toast — quiet ink pill, bottom of screen. Non-blocking feedback.
// Mount <ToastHost /> once at the app root. Trigger via `toast.show(...)`.
import { Feather } from "@expo/vector-icons";
import { useEffect, useRef, useState } from "react";
import { Animated, Easing, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

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

const INK = "#1D1B16";
const OK = "#7FBF97";
const RISK = "#E8A198";

export function ToastHost() {
  const [ev, setEv] = useState<ToastEvent | null>(null);
  const anim = useRef(new Animated.Value(0)).current;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const insets = useSafeAreaInsets();

  useEffect(() => {
    const l = (e: ToastEvent) => {
      setEv(e);
      Animated.timing(anim, { toValue: 1, duration: 200, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        Animated.timing(anim, { toValue: 0, duration: 160, easing: Easing.in(Easing.cubic), useNativeDriver: true }).start(({ finished }) => {
          if (finished) setEv(null);
        });
      }, 2600);
    };
    listeners.push(l);
    return () => { listeners = listeners.filter((x) => x !== l); };
  }, [anim]);

  if (!ev) return null;
  const iconColor = ev.kind === "success" ? OK : ev.kind === "error" ? RISK : "rgba(255,255,255,0.75)";
  const icon = ev.kind === "success" ? "check" : ev.kind === "error" ? "alert-circle" : "info";

  return (
    <View pointerEvents="none" style={[styles.host, { bottom: Math.max(insets.bottom, 12) + 76 }]}>
      <Animated.View
        style={[styles.toast, {
          opacity: anim,
          transform: [{ translateY: anim.interpolate({ inputRange: [0, 1], outputRange: [8, 0] }) }],
        }]}
      >
        <Feather name={icon as any} size={15} color={iconColor} />
        <Text style={styles.text} numberOfLines={2}>{ev.text}</Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  host: { position: "absolute", left: 0, right: 0, alignItems: "center", zIndex: 9999 },
  toast: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999,
    backgroundColor: INK, maxWidth: 440,
    shadowColor: "#26221B", shadowOpacity: 0.24, shadowOffset: { width: 0, height: 10 }, shadowRadius: 28, elevation: 10,
  },
  text: { color: "#FFFFFF", fontFamily: "Inter-Medium", fontWeight: "500", fontSize: 13.5, flexShrink: 1 },
});
