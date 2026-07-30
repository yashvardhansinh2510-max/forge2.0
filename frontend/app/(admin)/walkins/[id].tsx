// Walk-in detail — Phase 4 (2026-07-30). Status transitions, notes, and the
// Customer Timeline (reused via services/activity_log.timeline_for — same
// audit trail every other module already writes to, nothing new to render
// beyond a generic event list).
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Linking, Platform, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { walkinsApi, type WalkIn } from "@/src/api/walkins";
import { toast } from "@/src/components/Toast";
import { Button, Card, PageHeader, Skeleton, TextField } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme/tokens";

async function openUrl(url: string) {
  if (Platform.OS === "web") {
    // @ts-ignore — web only
    window.open(url, "_blank");
  } else {
    await Linking.openURL(url);
  }
}

const NEXT_STATUS: Record<string, { value: string; label: string }[]> = {
  new: [{ value: "contacted", label: "Mark Contacted" }],
  contacted: [{ value: "selection_scheduled", label: "Schedule Selection" }],
  selection_scheduled: [{ value: "contacted", label: "Reschedule" }],
};

export default function WalkInDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [w, setW] = useState<WalkIn | null>(null);
  const [timeline, setTimeline] = useState<Record<string, any>[]>([]);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [detail, tl] = await Promise.all([walkinsApi.get(id), walkinsApi.timeline(id)]);
      setW(detail); setNotes(detail.notes || ""); setTimeline(tl);
    } catch (e: any) {
      toast.error(e?.detail || "Could not load Walk-in");
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const updateStatus = async (status: string, lostReason?: string) => {
    setBusy(true);
    try {
      await walkinsApi.update(id, { status: status as any, ...(lostReason ? { lost_reason: lostReason } : {}) });
      toast.success("Walk-in updated");
      load();
    } catch (e: any) {
      toast.error(e?.detail || "Could not update Walk-in");
    } finally {
      setBusy(false);
    }
  };

  const saveNotes = async () => {
    setBusy(true);
    try {
      await walkinsApi.update(id, { notes });
      toast.success("Notes saved");
    } catch (e: any) {
      toast.error(e?.detail || "Could not save notes");
    } finally {
      setBusy(false);
    }
  };

  const whatsApp = async () => {
    try {
      const res = await walkinsApi.contact(id, "whatsapp");
      if (res.wa_url) await openUrl(res.wa_url);
    } catch (e: any) {
      toast.error(e?.detail || "Could not open WhatsApp");
    }
  };

  if (!w) {
    return (
      <SafeAreaView style={{ flex: 1 }} edges={["top"]}>
        <PageHeader title="Walk-in" back={() => router.back()} />
        <View style={{ padding: spacing.xl }}><Skeleton h={120} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1 }} edges={["top"]}>
      <PageHeader title={w.customer_name} overline={w.number} back={() => router.back()} />
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }}>
        <Card variant="outlined" style={{ gap: 4 }}>
          <Text style={type.bodyStrong}>{w.customer_phone} {w.alternate_phone ? `· Alt: ${w.alternate_phone}` : ""}</Text>
          <Text style={type.bodyMuted}>{w.source} · {(w.interested_products || []).join(", ") || "No products noted"}</Text>
          {w.budget ? <Text style={type.bodySm}>Budget: ₹{w.budget.toLocaleString("en-IN")}</Text> : null}
          <Text style={[type.captionStrong, { color: colors.brandHover, marginTop: 4 }]}>Status: {w.status.replace(/_/g, " ")}</Text>
        </Card>

        <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
          <Button label="Call" icon="phone" variant="secondary" size="sm" onPress={() => w.customer_phone && openUrl(`tel:${w.customer_phone}`)} />
          <Button label="WhatsApp" icon="message-circle" variant="secondary" size="sm" onPress={whatsApp} />
          {(NEXT_STATUS[w.status] || []).map((s) => (
            <Button key={s.value} label={s.label} variant="secondary" size="sm" loading={busy} onPress={() => updateStatus(s.value)} />
          ))}
          {w.status !== "converted" && w.status !== "lost" ? (
            <Button label="Mark Converted" size="sm" loading={busy} onPress={() => updateStatus("converted")} testID="walkin-mark-converted" />
          ) : null}
          {w.status !== "converted" && w.status !== "lost" ? (
            <Button label="Mark Lost" variant="danger" size="sm" loading={busy} onPress={() => updateStatus("lost", "Not interested")} testID="walkin-mark-lost" />
          ) : null}
        </View>

        <TextField label="Notes" value={notes} onChangeText={setNotes} multiline numberOfLines={3} />
        <Button label="Save Notes" variant="secondary" size="sm" onPress={saveNotes} loading={busy} />

        <Text style={type.bodyStrong}>Customer Timeline</Text>
        {timeline.length === 0 ? (
          <Text style={type.bodyMuted}>No activity yet.</Text>
        ) : (
          timeline.map((ev, i) => (
            <Card key={ev.id || i} variant="outlined" style={{ gap: 2 }}>
              <Text style={type.bodySm}>{ev.summary || ev.event_type}</Text>
              <Text style={type.caption}>{(ev.created_at || "").toString().slice(0, 16).replace("T", " ")}</Text>
            </Card>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}
