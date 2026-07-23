// Customer Portal — Dashboard. Intentionally minimal (Phase 5 roadmap):
// name, contact details, latest quotation, total quotation count, and a
// single way in to the full list. No purchases/payments/reports/inventory —
// this portal is a secure, read-only document portal, nothing else.
import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { Button, Card, Skeleton, StatusBadge } from "@/src/components/ui";
import { BuildConLogo } from "@/src/design/BrandLogo";
import { useAuth } from "@/src/state/auth";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

const HERO = "https://images.pexels.com/photos/6957081/pexels-photo-6957081.jpeg?auto=compress&cs=tinysrgb&w=1600";

type Quote = { id: string; number: string; status: string; grand_total: number; created_at: string; items: any[]; valid_until?: string; revisions?: any[] };
type Profile = { name: string; company?: string; phone?: string; email?: string };

export default function CustomerDashboard() {
  const { customer, logout } = useAuth();
  const router = useRouter();
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);

  useEffect(() => {
    api.get<Quote[]>("/portal/quotations").then(setQuotes).catch(() => setQuotes([]));
    api.get<Profile>("/auth/customer/me").then(setProfile).catch(() => {});
  }, []);

  const latest = quotes && quotes.length > 0 ? quotes[0] : null;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 40 }}>
        {/* Hero */}
        <View style={{ height: 240, backgroundColor: colors.surfaceInverse }}>
          <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" transition={300} />
          <LinearGradient colors={["rgba(9,9,11,0.1)", "rgba(9,9,11,0.85)"]} style={StyleSheet.absoluteFill} />

          <View style={{ flex: 1, padding: spacing.xl, justifyContent: "space-between" }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                <BuildConLogo height={34} />
              </View>
              <Pressable
                testID="portal-logout"
                onPress={async () => { await logout(); router.replace("/(auth)/login"); }}
                style={styles.logoutPill}
              >
                <Feather name="log-out" size={13} color="#fff" />
                <Text style={{ color: "#fff", fontSize: 12, fontWeight: "600" }}>Sign out</Text>
              </Pressable>
            </View>

            <View style={{ gap: 4 }}>
              <Text style={{ color: "rgba(255,255,255,0.8)", fontSize: 13, letterSpacing: 1.2, fontWeight: "600" }}>WELCOME</Text>
              <Text style={{ color: "#fff", fontSize: 30, fontWeight: "700", letterSpacing: -0.3 }} numberOfLines={1}>
                {customer?.company || customer?.name}
              </Text>
            </View>
          </View>
        </View>

        {/* Content */}
        <View style={{ padding: spacing.xl, gap: spacing.lg }}>
          {/* Contact details */}
          <Card style={{ gap: 10 }}>
            <Text style={type.overline}>Your account</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
              <Feather name="user" size={15} color={colors.onSurfaceMuted} />
              <Text style={type.bodyStrong}>{customer?.name}</Text>
            </View>
            {profile?.phone ? (
              <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                <Feather name="phone" size={15} color={colors.onSurfaceMuted} />
                <Text style={type.body}>{profile.phone}</Text>
              </View>
            ) : null}
            {(profile?.email || customer?.email) ? (
              <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                <Feather name="mail" size={15} color={colors.onSurfaceMuted} />
                <Text style={type.body}>{profile?.email || customer?.email}</Text>
              </View>
            ) : null}
          </Card>

          {/* Latest quotation + count */}
          <View>
            <Text style={type.overline}>Latest quotation</Text>
          </View>

          {!quotes ? (
            <Card style={{ gap: 12 }}>
              <Skeleton w="40%" />
              <Skeleton w="80%" h={22} />
              <Skeleton w="30%" />
            </Card>
          ) : !latest ? (
            <Card style={{ alignItems: "center", gap: 6, paddingVertical: spacing.xl }}>
              <Feather name="file-text" size={22} color={colors.onSurfaceMuted} />
              <Text style={type.bodyStrong}>No quotations yet</Text>
              <Text style={[type.caption, { textAlign: "center" }]}>Your sales representative will share estimates here.</Text>
            </Card>
          ) : (
            <Card onPress={() => router.push(`/(customer)/quotes/${latest.id}`)} style={{ gap: 4 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <View style={{ flex: 1 }}>
                  <Text style={[type.mono, { color: colors.onSurfaceMuted }]}>{latest.number}</Text>
                  <Text style={[type.titleMd, { marginTop: 2 }]}>{latest.items.length} items · {new Date(latest.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}</Text>
                </View>
                <StatusBadge status={latest.status} />
              </View>
              <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: spacing.md }} />
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <View>
                  <Text style={type.caption}>Grand total</Text>
                  <Text style={{ fontSize: 22, fontWeight: "700", fontVariant: ["tabular-nums"] }} numberOfLines={1}>{money(latest.grand_total)}</Text>
                </View>
                <Button testID="latest-view-btn" label="View" icon="arrow-right" size="sm" variant="secondary" onPress={() => router.push(`/(customer)/quotes/${latest.id}`)} />
              </View>
            </Card>
          )}

          <Button
            testID="view-all-quotations-btn"
            label={quotes ? `View all quotations (${quotes.length})` : "View all quotations"}
            icon="list"
            variant="secondary"
            fullWidth
            onPress={() => router.push("/(customer)/quotes")}
          />

          {/* Contact support floating card */}
          <Card style={styles.support}>
            <View style={{ flex: 1 }}>
              <Text style={[type.titleMd, { color: colors.onSurfaceInverse }]}>Need help?</Text>
              <Text style={{ color: "rgba(255,255,255,0.72)", fontSize: 13, marginTop: 2 }}>Talk to your BuildCon House representative.</Text>
            </View>
            <Pressable testID="portal-support-btn" onPress={() => Linking.openURL("mailto:support@forge.app")} style={styles.supportBtnPrimary}>
              <Feather name="message-circle" size={14} color={colors.brand} />
              <Text style={{ color: colors.brand, fontSize: 13, fontWeight: "700" }}>Contact</Text>
            </Pressable>
          </Card>

          <View style={{ flexDirection: "row", justifyContent: "center", gap: spacing.lg, paddingTop: spacing.sm }}>
            <Pressable testID="portal-privacy-link" onPress={() => router.push("/privacy")} hitSlop={8}>
              <Text style={{ fontSize: 12, color: colors.onSurfaceMuted }}>Privacy</Text>
            </Pressable>
            <Pressable testID="portal-terms-link" onPress={() => router.push("/terms")} hitSlop={8}>
              <Text style={{ fontSize: 12, color: colors.onSurfaceMuted }}>Terms</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  logoutPill: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 999, backgroundColor: "rgba(255,255,255,0.14)", borderWidth: 1, borderColor: "rgba(255,255,255,0.24)",
  },
  support: {
    backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse,
    flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg,
  },
  supportBtnPrimary: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 9,
    backgroundColor: "#fff", borderRadius: radius.md,
  },
});
