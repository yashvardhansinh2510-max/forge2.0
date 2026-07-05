// BuildCon House · Sign in
// Premium two-pane on tablet, single-column on phone. Blue accent + Inter.

import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView, Platform, ScrollView, StyleSheet,
  Text, TouchableOpacity, useWindowDimensions, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Alert as UIAlert, BrandMark, Button, SegmentedControl, TextField } from "@/src/components/ui";
import { useAuth } from "@/src/state/auth";
import { brand, colors, radius, spacing, type } from "@/src/theme/tokens";

const HERO = "https://images.pexels.com/photos/7045908/pexels-photo-7045908.jpeg?auto=compress&cs=tinysrgb&w=1400";

export default function Login() {
  const { loginStaff, loginCustomer } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 780;

  const [portal, setPortal] = useState<"staff" | "customer">("staff");
  const [email, setEmail] = useState("owner@forge.app");
  const [password, setPassword] = useState("Forge@2026");
  const [showPass, setShowPass] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const swap = (p: "staff" | "customer") => {
    setPortal(p);
    setError(null);
    setEmail(p === "customer" ? "customer@forge.app" : "owner@forge.app");
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
        colors={["rgba(15,23,42,0.25)", "rgba(15,23,42,0.92)"]}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView edges={["top", "left"]} style={{ flex: 1, padding: spacing.xxl, justifyContent: "space-between" }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
          <BrandMark size={40} inverse />
          <View>
            <Text style={styles.brandName}>{brand.name}</Text>
            <Text style={styles.brandTagline}>{brand.tagline}</Text>
          </View>
        </View>
        <View style={{ gap: spacing.md, paddingBottom: spacing.xl, maxWidth: 520 }}>
          <Text style={styles.heroTitle}>
            The operating system for premium sanitaryware.
          </Text>
          <Text style={styles.heroSub}>
            Quotations in seconds. Catalogues in sync. Customers delighted.
            Built with the standards of Linear, Stripe, and Apple.
          </Text>
        </View>
      </SafeAreaView>
    </View>
  );

  const FormSide = (
    <SafeAreaView edges={["top", "bottom", "right"]} style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{ flexGrow: 1, justifyContent: "center", padding: spacing.xxl }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={{ maxWidth: 420, width: "100%", alignSelf: "center", gap: spacing.lg }}>
          {!isTablet ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, marginBottom: spacing.sm }}>
              <BrandMark size={40} />
              <View>
                <Text style={styles.brandNameDark}>{brand.name}</Text>
                <Text style={type.caption}>{brand.tagline}</Text>
              </View>
            </View>
          ) : null}

          <View style={{ gap: 6 }}>
            <Text style={type.displayMd}>Welcome back</Text>
            <Text style={type.bodyMuted}>Choose your portal and continue.</Text>
          </View>

          <SegmentedControl
            value={portal}
            onChange={swap}
            fullWidth
            testID="portal-segment"
            options={[
              { value: "staff",    label: "Team Portal",     icon: "briefcase" },
              { value: "customer", label: "Customer Portal", icon: "user" },
            ]}
          />

          <TextField
            testID="login-email-input"
            label="Email"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            placeholder="you@company.com"
            leftIcon="mail"
          />

          <TextField
            testID="login-password-input"
            label="Password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry={!showPass}
            placeholder="••••••••"
            leftIcon="lock"
            rightIcon={showPass ? "eye-off" : "eye"}
            onRightPress={() => setShowPass((v) => !v)}
            onSubmitEditing={submit}
          />

          {error ? (
            <UIAlert tone="error" title="Couldn’t sign in" description={error} />
          ) : null}

          <Button
            testID="login-submit-button"
            label={submitting ? "Signing in…" : "Sign in"}
            onPress={submit}
            loading={submitting}
            fullWidth
            size="lg"
            iconRight="arrow-right"
          />

          <View style={styles.demoCard}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Feather name="info" size={12} color={colors.onSurfaceMuted} />
              <Text style={type.overline}>Demo credentials</Text>
            </View>
            <Text style={[type.caption, { lineHeight: 18 }]}>
              {portal === "staff"
                ? "owner@forge.app · admin@forge.app · sales@forge.app (etc.)"
                : "customer@forge.app"}
              {"  ·  "}
              <Text style={{ fontFamily: Platform.select({ ios: "Menlo", android: "monospace" }) }}>Forge@2026</Text>
            </Text>
            {portal === "staff" ? (
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                {["owner", "admin", "manager", "sales", "purchase", "warehouse", "accounts", "worker"].map((r) => (
                  <TouchableOpacity
                    key={r}
                    onPress={() => setEmail(`${r}@forge.app`)}
                    testID={`quick-${r}`}
                    style={styles.rolePill}
                  >
                    <Text style={styles.rolePillText}>{r}</Text>
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
          <View style={{ height: 240 }}>{HeroSide}</View>
          <View style={{ flex: 1 }}>{FormSide}</View>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  brandName: {
    color: colors.onSurfaceInverse,
    fontSize: 17,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "700",
    letterSpacing: -0.2,
  },
  brandNameDark: {
    color: colors.onSurface,
    fontSize: 17,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "700",
    letterSpacing: -0.2,
  },
  brandTagline: {
    color: "rgba(255,255,255,0.72)",
    fontSize: 12,
    fontFamily: type.caption.fontFamily,
    marginTop: 2,
  },
  heroTitle: {
    color: colors.onSurfaceInverse,
    fontSize: 34,
    lineHeight: 42,
    letterSpacing: -0.6,
    fontFamily: type.displayLg.fontFamily,
    fontWeight: "700",
  },
  heroSub: {
    color: "rgba(255,255,255,0.75)",
    fontSize: 15,
    lineHeight: 22,
    fontFamily: type.body.fontFamily,
  },
  demoCard: {
    padding: spacing.md,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    gap: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  rolePill: {
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  rolePillText: {
    fontSize: 11,
    fontFamily: type.captionStrong.fontFamily,
    color: colors.onSurfaceSecondary,
    fontWeight: "500",
    letterSpacing: 0.1,
  },
});
