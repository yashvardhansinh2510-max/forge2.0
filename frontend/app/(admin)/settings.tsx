// BuildCon House · Settings
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Avatar, Card } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/state/auth";
import { brand, colors, radius, roleLabels, spacing, type } from "@/src/theme/tokens";

type SessionInfo = {
  id: string; device_label?: string | null; login_method: string;
  created_at: string; last_seen_at: string; current: boolean;
};

export default function Settings() {
  const { staff, logout } = useAuth();
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [revoking, setRevoking] = useState(false);

  const loadSessions = useCallback(async () => {
    try {
      const list = await api.get<SessionInfo[]>("/auth/sessions");
      setSessions(list);
    } catch {
      setSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  const doLogoutAll = async () => {
    setRevoking(true);
    try {
      await api.post("/auth/sessions/logout-all");
      await logout();
      router.replace("/(auth)/login");
    } catch {
      setRevoking(false);
    }
  };

  const confirmLogoutAll = () => {
    if (Platform.OS === "web") {
      // eslint-disable-next-line no-alert
      if (window.confirm("Sign out of every device where you're logged in?")) doLogoutAll();
      return;
    }
    Alert.alert("Log out everywhere?", "You'll be signed out on every device, including this one.", [
      { text: "Cancel", style: "cancel" },
      { text: "Log out everywhere", style: "destructive", onPress: doLogoutAll },
    ]);
  };

  const revokeOne = async (id: string) => {
    try {
      await api.delete(`/auth/sessions/${id}`);
      setSessions((cur) => cur.filter((s) => s.id !== id));
    } catch { /* best-effort */ }
  };

  const timeAgo = (iso: string) => {
    const diffMs = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  const sections = [
    { title: "Profile", items: [
      { label: "Name", value: staff?.full_name, icon: "user" as const },
      { label: "Email", value: staff?.email, icon: "mail" as const },
      { label: "Role", value: roleLabels[staff?.role || ""], icon: "shield" as const },
    ] },
    { title: "Organization", items: [
      { label: "Company", value: brand.name, icon: "home" as const },
      { label: "Plan", value: "Founding — Unlimited", icon: "star" as const },
      { label: "Time zone", value: "Asia/Kolkata (GMT+5:30)", icon: "clock" as const },
    ] },
  ];

  return (
    <AdminPage title="Settings" subtitle="Profile, organization & preferences">
      {/* Profile hero */}
      <View style={styles.hero}>
        <Avatar name={staff?.full_name} size={64} tone="brand" />
        <View style={{ alignItems: "center", gap: 4 }}>
          <Text style={type.titleLg}>{staff?.full_name || "—"}</Text>
          <Text style={type.bodyMuted}>{staff?.email}</Text>
          <View style={styles.rolePill}>
            <Feather name="shield" size={11} color={colors.brand} />
            <Text style={styles.rolePillText}>{roleLabels[staff?.role || ""] || staff?.role || "Team"}</Text>
          </View>
        </View>
      </View>

      {sections.map((s) => (
        <Card key={s.title} style={{ padding: 0 }} variant="flat">
          <Text style={[type.overline, { padding: spacing.md, paddingBottom: 8 }]}>{s.title}</Text>
          {s.items.map((it, i) => (
            <View
              key={it.label}
              style={[styles.row, i === 0 ? null : { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.divider }]}
            >
              <View style={styles.itemIcon}>
                <Feather name={it.icon} size={14} color={colors.onSurfaceMuted} />
              </View>
              <Text style={[type.bodyMuted, { flex: 1 }]}>{it.label}</Text>
              <Text style={{
                fontSize: 14,
                fontFamily: type.bodyStrong.fontFamily,
                fontWeight: "500",
                color: colors.onSurface,
              }}>{it.value || "—"}</Text>
            </View>
          ))}
        </Card>
      ))}

      {/* Security — active sessions / trusted devices */}
      <Card style={{ padding: 0 }} variant="flat">
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: spacing.md, paddingBottom: 8 }}>
          <Text style={type.overline}>Security · Active sessions</Text>
          {sessionsLoading ? <ActivityIndicator size="small" color={colors.onSurfaceMuted} /> : null}
        </View>
        {!sessionsLoading && sessions.length === 0 ? (
          <Text style={[type.bodyMuted, { padding: spacing.md, paddingTop: 0 }]}>No active sessions found.</Text>
        ) : sessions.map((s, i) => (
          <View
            key={s.id}
            style={[styles.row, i === 0 ? null : { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.divider }]}
          >
            <View style={styles.itemIcon}>
              <Feather name={s.login_method === "google" ? "smartphone" : "monitor"} size={14} color={colors.onSurfaceMuted} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13.5, fontWeight: "600", color: colors.onSurface }}>
                {s.device_label || "Unknown device"} {s.current ? "· This device" : ""}
              </Text>
              <Text style={type.caption}>
                {s.login_method === "google" ? "Google" : "Password"} · Active {timeAgo(s.last_seen_at)}
              </Text>
            </View>
            {!s.current ? (
              <Pressable testID={`revoke-session-${s.id}`} hitSlop={8} onPress={() => revokeOne(s.id)}>
                <Feather name="x-circle" size={16} color={colors.onSurfaceMuted} />
              </Pressable>
            ) : null}
          </View>
        ))}
        <Pressable
          testID="logout-all-devices"
          onPress={confirmLogoutAll}
          disabled={revoking}
          style={({ pressed }) => [styles.logoutAllRow, { opacity: pressed || revoking ? 0.7 : 1 }]}
        >
          <Feather name="shield-off" size={14} color={colors.error} />
          <Text style={styles.logoutAllLabel}>{revoking ? "Signing out everywhere…" : "Log out of all devices"}</Text>
        </Pressable>
      </Card>

      <Pressable
        testID="settings-logout"
        onPress={async () => { await logout(); router.replace("/(auth)/login"); }}
        style={({ pressed }) => [styles.logout, { opacity: pressed ? 0.88 : 1 }]}
      >
        <Feather name="log-out" size={16} color={colors.error} />
        <Text style={{
          color: colors.error,
          fontSize: 14,
          fontFamily: type.titleMd.fontFamily,
          fontWeight: "600",
        }}>Sign out</Text>
      </Pressable>

      <Text style={[type.caption, { textAlign: "center", marginTop: spacing.sm }]}>
        {brand.name} · {brand.tagline}
      </Text>
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  hero: {
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  rolePill: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTint,
    marginTop: 4,
  },
  rolePillText: {
    fontSize: 11,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "600",
    color: colors.brand,
    letterSpacing: 0.1,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
  },
  itemIcon: {
    width: 32, height: 32, borderRadius: 10,
    backgroundColor: colors.surfaceTertiary,
    alignItems: "center", justifyContent: "center",
  },
  logout: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 8,
    padding: spacing.md,
    backgroundColor: colors.errorBg,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.errorBorder,
  },
});
