import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet,
  Text, TextInput, TouchableOpacity, useWindowDimensions, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button } from "@/src/components/ui";
import { useAuth } from "@/src/state/auth";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

const HERO = "https://images.pexels.com/photos/7045908/pexels-photo-7045908.jpeg?auto=compress&cs=tinysrgb&w=1400";

export default function Login() {
  const { loginStaff, loginCustomer } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 780;

  const [portal, setPortal] = useState<"staff" | "customer">("staff");
  const [email, setEmail] = useState("owner@forge.app");
  const [password, setPassword] = useState("Forge@2026");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const swap = (p: "staff" | "customer") => {
    setPortal(p);
    setError(null);
    if (p === "customer") {
      setEmail("customer@forge.app");
    } else {
      setEmail("owner@forge.app");
    }
    setPassword("Forge@2026");
  };

  const submit = async () => {
    setError(null); setSubmitting(true);
    try {
      if (portal === "staff") await loginStaff(email.trim().toLowerCase(), password);
      else await loginCustomer(email.trim().toLowerCase(), password);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace(portal === "staff" ? "/(admin)/dashboard" : "/(customer)/home");
    } catch (e: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setError(e.detail || e.message || "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  };

  const HeroSide = (
    <View style={{ flex: 1, backgroundColor: colors.surfaceInverse }}>
      <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" transition={300} />
      <LinearGradient
        colors={["rgba(9,9,11,0.15)", "rgba(9,9,11,0.85)"]}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView edges={["top", "left"]} style={{ flex: 1, padding: spacing.xxl, justifyContent: "space-between" }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
          <View style={styles.brandMark}><Text style={styles.brandMarkText}>F</Text></View>
          <Text style={{ color: "#fff", fontSize: 18, fontWeight: "700", letterSpacing: 1.2 }}>FORGE</Text>
        </View>
        <View style={{ gap: spacing.md, paddingBottom: spacing.xl }}>
          <Text style={{ color: "#fff", fontSize: 40, fontWeight: "700", lineHeight: 46, letterSpacing: -0.5 }}>
            The operating system for premium sanitaryware.
          </Text>
          <Text style={{ color: "rgba(255,255,255,0.72)", fontSize: 15, lineHeight: 22, maxWidth: 480 }}>
            Quotations in seconds. Catalogs in sync. Customers delighted. Built with the standards of Linear, Stripe, and Apple.
          </Text>
        </View>
      </SafeAreaView>
    </View>
  );

  const FormSide = (
    <SafeAreaView edges={["top", "bottom", "right"]} style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: "center", padding: spacing.xxl }} keyboardShouldPersistTaps="handled">
        <View style={{ maxWidth: 420, width: "100%", alignSelf: "center", gap: spacing.lg }}>
          {!isTablet ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md }}>
              <View style={[styles.brandMark, { backgroundColor: colors.brand }]}><Text style={[styles.brandMarkText, { color: colors.onBrand }]}>F</Text></View>
              <Text style={{ fontSize: 16, fontWeight: "700", letterSpacing: 1.2, color: colors.onSurface }}>FORGE</Text>
            </View>
          ) : null}

          <View>
            <Text style={type.displayMd}>Sign in to Forge</Text>
            <Text style={[type.bodyMuted, { marginTop: 4 }]}>Choose your portal and continue.</Text>
          </View>

          {/* Segmented control */}
          <View style={styles.segment}>
            {(["staff", "customer"] as const).map((p) => (
              <Pressable
                key={p}
                onPress={() => swap(p)}
                testID={`portal-${p}-tab`}
                style={[styles.segItem, portal === p && styles.segActive]}
              >
                <Feather name={p === "staff" ? "briefcase" : "user"} size={14} color={portal === p ? colors.onBrand : colors.onSurfaceMuted} />
                <Text style={{ color: portal === p ? colors.onBrand : colors.onSurfaceMuted, fontSize: 13, fontWeight: "600" }}>
                  {p === "staff" ? "Team Portal" : "Customer Portal"}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={{ gap: spacing.sm }}>
            <Text style={type.overline}>Email</Text>
            <TextInput
              testID="login-email-input"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              placeholder="you@company.com"
              placeholderTextColor={colors.onSurfaceMuted}
              style={styles.input}
            />
          </View>

          <View style={{ gap: spacing.sm }}>
            <Text style={type.overline}>Password</Text>
            <TextInput
              testID="login-password-input"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              placeholder="••••••••"
              placeholderTextColor={colors.onSurfaceMuted}
              style={styles.input}
              onSubmitEditing={submit}
            />
          </View>

          {error ? (
            <View style={{ backgroundColor: colors.errorBg, padding: spacing.md, borderRadius: radius.md, flexDirection: "row", gap: 8, alignItems: "center" }}>
              <Feather name="alert-triangle" size={14} color={colors.error} />
              <Text style={{ color: colors.error, fontSize: 13, flex: 1 }}>{error}</Text>
            </View>
          ) : null}

          <Button
            testID="login-submit-button"
            label={submitting ? "Signing in…" : "Sign in"}
            onPress={submit}
            loading={submitting}
            fullWidth
            size="lg"
          />

          <View style={{ padding: spacing.md, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, gap: 4 }}>
            <Text style={type.overline}>Demo credentials</Text>
            <Text style={type.caption}>
              {portal === "staff"
                ? "owner@forge.app · admin@forge.app · sales@forge.app · (etc.)"
                : "customer@forge.app"}
              {"  ·  "}
              <Text style={{ fontFamily: Platform.select({ ios: "Menlo", android: "monospace" }) }}>Forge@2026</Text>
            </Text>
            {portal === "staff" ? (
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
                {["owner", "admin", "manager", "sales", "purchase", "warehouse", "accounts", "worker"].map((r) => (
                  <TouchableOpacity
                    key={r}
                    onPress={() => setEmail(`${r}@forge.app`)}
                    testID={`quick-${r}`}
                    style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border }}
                  >
                    <Text style={{ fontSize: 11, color: colors.onSurfaceSecondary, fontWeight: "500" }}>{r}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            ) : null}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
      {isTablet ? (
        <View style={{ flex: 1, flexDirection: "row" }}>
          <View style={{ flex: 1 }}>{HeroSide}</View>
          <View style={{ flex: 1 }}>{FormSide}</View>
        </View>
      ) : (
        <View style={{ flex: 1 }}>
          <View style={{ height: 220 }}>{HeroSide}</View>
          <View style={{ flex: 1 }}>{FormSide}</View>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  brandMark: {
    width: 32, height: 32, borderRadius: 8, backgroundColor: "rgba(255,255,255,0.14)",
    alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "rgba(255,255,255,0.24)",
  },
  brandMarkText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  segment: {
    flexDirection: "row", backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: 4, gap: 4,
  },
  segItem: {
    flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    paddingVertical: 9, borderRadius: 10,
  },
  segActive: { backgroundColor: colors.brand },
  input: {
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, color: colors.onSurface,
  },
});
