import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useEffect, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";

import { Badge, Button, Card, EmptyState, Skeleton, StatusBadge } from "@/src/components/ui";
import { api, getToken } from "@/src/api/client";
import { useAuth } from "@/src/state/auth";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

const HERO = "https://images.pexels.com/photos/6957081/pexels-photo-6957081.jpeg?auto=compress&cs=tinysrgb&w=1600";

type Quote = { id: string; number: string; status: string; grand_total: number; created_at: string; items: any[]; valid_until?: string };

export default function CustomerHome() {
  const { customer, logout } = useAuth();
  const router = useRouter();
  const [quotes, setQuotes] = useState<Quote[] | null>(null);

  useEffect(() => {
    api.get<Quote[]>("/portal/quotations").then(setQuotes).catch(() => setQuotes([]));
  }, []);

  const downloadPdf = async (id: string) => {
    const token = await getToken();
    if (!token) return;
    try {
      const res = await fetch(`${api.base}/api/quotations/${id}/portal-pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const blob = await res.blob();
      const reader = new FileReader();
      reader.onloadend = () => Linking.openURL(reader.result as string);
      reader.readAsDataURL(blob);
    } catch {}
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 40 }}>
        {/* Hero */}
        <View style={{ height: 280, backgroundColor: colors.surfaceInverse }}>
          <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" transition={300} />
          <LinearGradient colors={["rgba(9,9,11,0.1)", "rgba(9,9,11,0.85)"]} style={StyleSheet.absoluteFill} />

          <View style={{ flex: 1, padding: spacing.xl, justifyContent: "space-between" }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                <View style={styles.brandMark}><Text style={styles.brandMarkText}>F</Text></View>
                <Text style={{ color: "#fff", fontSize: 15, fontWeight: "700", letterSpacing: 1.2 }}>FORGE</Text>
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
              <Text style={{ color: "#fff", fontSize: 32, fontWeight: "700", letterSpacing: -0.3 }} numberOfLines={1}>
                {customer?.company || customer?.name}
              </Text>
              <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 14 }}>
                Your quotations, catalogs and support — beautifully in one place.
              </Text>
            </View>
          </View>
        </View>

        {/* Content */}
        <View style={{ padding: spacing.xl, gap: spacing.lg }}>
          <View>
            <Text style={type.overline}>Your quotations</Text>
            <Text style={type.titleLg}>Recent estimates</Text>
          </View>

          {!quotes ? (
            <>{Array.from({ length: 3 }).map((_, i) => (
              <Card key={i} style={{ gap: 12 }}>
                <Skeleton w="40%" />
                <Skeleton w="80%" h={22} />
                <Skeleton w="30%" />
              </Card>
            ))}</>
          ) : quotes.length === 0 ? (
            <EmptyState icon="file-text" title="No quotations yet" subtitle="Your sales representative will share estimates here." />
          ) : (
            quotes.map((q) => (
              <Card key={q.id} style={styles.quoteCard}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <View style={{ flex: 1 }}>
                    <Text style={[type.mono, { color: colors.onSurfaceMuted }]}>{q.number}</Text>
                    <Text style={[type.titleMd, { marginTop: 2 }]}>{q.items.length} items · {new Date(q.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}</Text>
                    {q.valid_until ? (
                      <Text style={type.caption}>Valid until {new Date(q.valid_until).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</Text>
                    ) : null}
                  </View>
                  <StatusBadge status={q.status} />
                </View>

                <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: spacing.md }} />

                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <View>
                    <Text style={type.caption}>Grand total</Text>
                    <Text style={{ fontSize: 24, fontWeight: "700", fontVariant: ["tabular-nums"] }}>{money(q.grand_total)}</Text>
                  </View>
                  <Button testID={`pdf-${q.id}`} label="Download PDF" icon="download" size="sm" onPress={() => downloadPdf(q.id)} />
                </View>
              </Card>
            ))
          )}

          {/* Contact support floating card */}
          <Card style={styles.support}>
            <View style={{ flex: 1 }}>
              <Text style={[type.titleMd, { color: colors.onSurfaceInverse }]}>Need help?</Text>
              <Text style={{ color: "rgba(255,255,255,0.72)", fontSize: 13, marginTop: 2 }}>Talk to your Forge representative or browse the catalog.</Text>
            </View>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Pressable testID="portal-catalog-btn" onPress={() => {}} style={styles.supportBtn}>
                <Feather name="grid" size={14} color={colors.onSurfaceInverse} />
                <Text style={styles.supportBtnText}>Catalog</Text>
              </Pressable>
              <Pressable testID="portal-support-btn" onPress={() => Linking.openURL("mailto:support@forge.app")} style={styles.supportBtnPrimary}>
                <Feather name="message-circle" size={14} color={colors.brand} />
                <Text style={{ color: colors.brand, fontSize: 13, fontWeight: "700" }}>Contact</Text>
              </Pressable>
            </View>
          </Card>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  brandMark: { width: 30, height: 30, borderRadius: 8, backgroundColor: "rgba(255,255,255,0.15)", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "rgba(255,255,255,0.24)" },
  brandMarkText: { color: "#fff", fontSize: 14, fontWeight: "700" },
  logoutPill: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 999, backgroundColor: "rgba(255,255,255,0.14)", borderWidth: 1, borderColor: "rgba(255,255,255,0.24)",
  },
  quoteCard: {},
  support: {
    backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse,
    flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg,
  },
  supportBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 9,
    backgroundColor: "rgba(255,255,255,0.12)", borderRadius: radius.md, borderWidth: 1, borderColor: "rgba(255,255,255,0.18)",
  },
  supportBtnText: { color: "#fff", fontSize: 13, fontWeight: "600" },
  supportBtnPrimary: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 9,
    backgroundColor: "#fff", borderRadius: radius.md,
  },
});
