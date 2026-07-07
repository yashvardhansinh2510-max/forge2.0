// ─────────────────────────────────────────────────────────────────────────────
// Authentication — one image, one form, one button.
// ─────────────────────────────────────────────────────────────────────────────
import { AntDesign } from "@expo/vector-icons";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import {
  ActivityIndicator, Keyboard, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button, Field, IconButton, Input, Txt } from "@/src/design/components";
import { useBp } from "@/src/design/responsive";
import { brand, color, font, radius, space } from "@/src/design/tokens";
import { useAuth } from "@/src/state/auth";

const HERO = "https://images.pexels.com/photos/36650049/pexels-photo-36650049.jpeg?auto=compress&cs=tinysrgb&w=1600";

type Mode = "staff" | "customer";

function GoogleButton({ label, onPress, loading }: { label: string; onPress: () => void; loading?: boolean }) {
  return (
    <Pressable
      testID="google-signin-button"
      onPress={loading ? undefined : onPress}
      disabled={loading}
      style={({ pressed, hovered }: any) => [
        styles.googleBtn,
        (pressed || hovered) && !loading && { backgroundColor: color.canvas },
        loading && { opacity: 0.6 },
      ]}
    >
      {loading ? (
        <ActivityIndicator size="small" color={color.ink} />
      ) : (
        <AntDesign name="google" size={16} color="#4285F4" />
      )}
      <Text style={styles.googleBtnLabel}>{label}</Text>
    </Pressable>
  );
}

function OrDivider() {
  return (
    <View style={styles.dividerRow}>
      <View style={styles.dividerLine} />
      <Text style={styles.dividerLabel}>OR</Text>
      <View style={styles.dividerLine} />
    </View>
  );
}

export default function Login() {
  const router = useRouter();
  const { loginStaff, loginCustomer, loginWithGoogle, googleBusy, googleError, clearGoogleError } = useAuth();
  const { isPhone, isTablet } = useBp();
  const insets = useSafeAreaInsets();

  const [mode, setMode] = useState<Mode>("staff");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!email.trim() || !password) { setError("Enter your email and password."); return; }
    Keyboard.dismiss();
    setBusy(true); setError(null);
    try {
      if (mode === "staff") {
        await loginStaff(email.trim(), password);
        router.replace("/(admin)/dashboard");
      } else {
        await loginCustomer(email.trim(), password);
        router.replace("/(customer)/home");
      }
    } catch (e: any) {
      setError(e?.message === "Invalid credentials" ? "That email and password don't match." : e?.message || "Sign-in failed. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const fillDemo = () => {
    if (mode === "staff") { setEmail("owner@forge.app"); setPassword("Forge@2026"); }
    else { setEmail("customer@forge.app"); setPassword("Forge@2026"); }
    setError(null);
  };

  const form = (
    <View style={{ width: "100%", maxWidth: 384, alignSelf: "center", gap: space.x5 }}>
      <View style={{ gap: 8 }}>
        {!isPhone ? <Txt v="eyebrow" tone="brass">{brand.name}</Txt> : null}
        <Txt v="display" style={isPhone ? { fontSize: 30, lineHeight: 38 } : undefined}>
          {mode === "staff" ? "Welcome back." : "Your project, live."}
        </Txt>
        <Txt v="bodyMid">
          {mode === "staff" ? "Sign in to your workspace." : "Sign in to follow your order."}
        </Txt>
      </View>

      <View style={{ gap: space.x4 }}>
        <GoogleButton
          label="Continue with Google"
          loading={googleBusy}
          onPress={() => { clearGoogleError(); setError(null); loginWithGoogle(mode); }}
        />
        {googleError ? <Text style={styles.googleErrorText}>{googleError}</Text> : null}

        <OrDivider />

        <Field label="Email">
          <Input
            testID="login-email"
            value={email}
            onChangeText={(v) => { setEmail(v); setError(null); }}
            placeholder="you@company.com"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            returnKeyType="next"
          />
        </Field>
        <Field label="Password" error={error}>
          <Input
            testID="login-password"
            value={password}
            onChangeText={(v) => { setPassword(v); setError(null); }}
            placeholder="••••••••"
            secureTextEntry={!showPw}
            autoCapitalize="none"
            autoComplete="password"
            returnKeyType="go"
            onSubmitEditing={submit}
            invalid={!!error}
            right={<IconButton icon={showPw ? "eye-off" : "eye"} size={30} iconSize={15} tone="soft" onPress={() => setShowPw((v) => !v)} label="Toggle password" />}
          />
        </Field>
        <Button testID="login-submit" label="Sign in" size="lg" full onPress={submit} loading={busy} />
      </View>

      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: space.x1 }}>
        <Pressable onPress={fillDemo} hitSlop={8}>
          <Text style={{ fontFamily: font.medium, fontSize: 13, color: color.inkSoft }}>Use demo account</Text>
        </Pressable>
        <Pressable
          testID="toggle-portal"
          onPress={() => { setMode((m) => (m === "staff" ? "customer" : "staff")); setError(null); clearGoogleError(); setEmail(""); setPassword(""); }}
          hitSlop={8}
        >
          <Text style={{ fontFamily: font.medium, fontSize: 13, color: color.brassDeep }}>
            {mode === "staff" ? "Customer portal →" : "← Staff sign-in"}
          </Text>
        </Pressable>
      </View>
    </View>
  );

  // ── Phone: image banner + form ──────────────────────────────────────────────
  if (isPhone) {
    return (
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: color.canvas }}>
        <ScrollView contentContainerStyle={{ flexGrow: 1 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <View style={{ height: 216 }}>
            <Image source={{ uri: HERO }} style={{ flex: 1 }} contentFit="cover" transition={300} />
            <LinearGradient colors={["rgba(20,17,12,0.05)", "rgba(20,17,12,0.55)"]} style={{ position: "absolute", left: 0, right: 0, top: 0, bottom: 0 }} />
            <View style={{ position: "absolute", left: 20, bottom: 16, right: 20 }}>
              <Text style={{ fontFamily: font.serif, fontSize: 20, color: "#FFFFFF" }}>{brand.name}</Text>
              <Text style={{ fontFamily: font.regular, fontSize: 12.5, color: "rgba(255,255,255,0.85)" }}>{brand.tagline}</Text>
            </View>
          </View>
          <View style={{ flex: 1, padding: 24, paddingTop: 32, paddingBottom: Math.max(24, insets.bottom + 16) }}>
            {form}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    );
  }

  // ── Tablet / desktop: split panel ───────────────────────────────────────────
  return (
    <View style={{ flex: 1, flexDirection: "row", backgroundColor: color.canvas }}>
      <View style={{ flex: isTablet ? 0.85 : 1.1 }}>
        <Image source={{ uri: HERO }} style={{ flex: 1 }} contentFit="cover" transition={400} />
        <LinearGradient
          colors={["rgba(20,17,12,0)", "rgba(20,17,12,0.62)"]}
          start={{ x: 0.5, y: 0.35 }}
          end={{ x: 0.5, y: 1 }}
          style={{ position: "absolute", left: 0, right: 0, top: 0, bottom: 0 }}
        />
        <View style={{ position: "absolute", left: 40, right: 40, bottom: 40, gap: 6 }}>
          <Text style={{ fontFamily: font.display, fontSize: 30, lineHeight: 38, color: "#FFFFFF", letterSpacing: -0.3 }}>
            {brand.tagline}.
          </Text>
          <Text style={{ fontFamily: font.regular, fontSize: 14, lineHeight: 21, color: "rgba(255,255,255,0.82)", maxWidth: 420 }}>
            The operating system for premium sanitaryware — quotations, orders and payments in one calm place.
          </Text>
        </View>
      </View>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, justifyContent: "center", padding: space.x10 }}>
        {form}
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  googleBtn: {
    height: 48, borderRadius: radius.md, borderWidth: 1, borderColor: color.line,
    backgroundColor: color.surface, flexDirection: "row", alignItems: "center",
    justifyContent: "center", gap: 10,
  },
  googleBtnLabel: { fontFamily: font.medium, fontSize: 14.5, color: color.ink },
  googleErrorText: { fontFamily: font.regular, fontSize: 12.5, color: "#B3261E", marginTop: -4 },
  dividerRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  dividerLine: { flex: 1, height: 1, backgroundColor: color.line },
  dividerLabel: { fontFamily: font.medium, fontSize: 11, letterSpacing: 0.6, color: color.inkSoft },
});
