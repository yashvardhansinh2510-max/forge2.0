// Settings > System — surfaces the existing GET /health/system backend
// (already fully working before this screen existed) so mongo/supabase
// connectivity, catalog counts, version, and warnings are visible in-app
// instead of only reachable via a raw API call.
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";

import { api } from "@/src/api/client";
import { AdminPage } from "@/src/components/AdminPage";
import { Card, Skeleton } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme/tokens";

type Health = {
  backend: string; version: string;
  mongo: { connected: boolean; is_local: boolean; error: string | null };
  supabase: { configured: boolean; connected: boolean; error: string | null };
  counts: Record<string, number>;
  warnings: string[];
  healthy: boolean;
};

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: ok ? colors.success : colors.error }} />
  );
}

export default function SettingsSystem() {
  const router = useRouter();
  const [health, setHealth] = useState<Health | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => api.get<Health>("/health/system").then(setHealth).catch(() => setHealth(null)), []);
  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <AdminPage title="System" subtitle="Live diagnostics — no configuration here, read-only" back={() => router.back()}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
        contentContainerStyle={{ gap: spacing.lg }}
      >
        {!health ? (
          <Card style={{ gap: 12 }}>
            <Skeleton w="60%" />
            <Skeleton w="100%" h={80} />
          </Card>
        ) : (
          <>
            <Card style={{ gap: spacing.md }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Text style={type.overline}>Overall</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <StatusDot ok={health.healthy} />
                  <Text style={type.bodyStrong}>{health.healthy ? "Healthy" : "Attention needed"}</Text>
                </View>
              </View>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={type.bodyMuted}>Version</Text>
                <Text style={type.body}>{health.version}</Text>
              </View>
            </Card>

            <Card style={{ gap: spacing.sm }}>
              <Text style={type.overline}>Connections</Text>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 6 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Feather name="database" size={14} color={colors.onSurfaceMuted} />
                  <Text style={type.body}>MongoDB{health.mongo.is_local ? " (local)" : " (Atlas)"}</Text>
                </View>
                <StatusDot ok={health.mongo.connected} />
              </View>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 6 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Feather name="hard-drive" size={14} color={colors.onSurfaceMuted} />
                  <Text style={type.body}>Supabase storage</Text>
                </View>
                <StatusDot ok={health.supabase.connected} />
              </View>
            </Card>

            <Card style={{ gap: spacing.sm }}>
              <Text style={type.overline}>Data</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
                {Object.entries(health.counts).map(([key, val]) => (
                  <View key={key} style={{ minWidth: 96 }}>
                    <Text style={{ fontSize: 20, fontWeight: "700" }}>{val}</Text>
                    <Text style={type.caption}>{key.replace(/_/g, " ")}</Text>
                  </View>
                ))}
              </View>
            </Card>

            {health.warnings.length > 0 ? (
              <Card style={{ gap: spacing.sm, backgroundColor: colors.warningBg, borderColor: colors.warningBorder }}>
                <Text style={type.overline}>Warnings</Text>
                {health.warnings.map((w, i) => (
                  <Text key={i} style={type.body}>• {w}</Text>
                ))}
              </Card>
            ) : null}
          </>
        )}
      </ScrollView>
    </AdminPage>
  );
}
