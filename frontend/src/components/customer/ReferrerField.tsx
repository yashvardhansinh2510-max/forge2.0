import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, Text, TextInput, View } from "react-native";

import { api } from "@/src/api/client";
import { Button, Sheet } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type Referrer = { id: string; name: string; type: "architect" | "interior_designer" };
type ReferrerValue = Pick<Referrer, "id" | "name" | "type"> | null;

export function ReferrerField({ value, onChange }: { value: ReferrerValue; onChange: (value: ReferrerValue) => void }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Referrer[]>([]);
  const [kind, setKind] = useState<Referrer["type"]>("architect");
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);

  useEffect(() => { if (open) api.get<Referrer[]>("/referrers").then(setItems).catch(() => setItems([])); }, [open]);
  const filtered = useMemo(() => items.filter((item) => item.type === kind), [items, kind]);
  const choose = (item: Referrer | null) => { onChange(item); setOpen(false); };
  const add = async () => {
    if (!name.trim()) return;
    setAdding(true);
    try {
      const created = await api.post<Referrer>("/referrers", { name: name.trim(), type: kind });
      setItems((current) => [...current, created]);
      choose(created);
    } finally { setAdding(false); }
  };

  return <View style={{ gap: 6 }}>
    <Text style={type.label}>Referred By</Text>
    <Pressable onPress={() => setOpen(true)} style={{ minHeight: 48, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, justifyContent: "center" }}>
      <Text style={type.body}>{value?.name || "Select architect or interior designer"}</Text>
    </Pressable>
    <Sheet visible={open} onClose={() => setOpen(false)} title="Referred By" variant="bottom" testID="customer-referrer-sheet">
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }} keyboardShouldPersistTaps="handled">
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          {(["architect", "interior_designer"] as const).map((option) => <Button key={option} label={option === "architect" ? "Architect" : "Interior designer"} variant={kind === option ? "primary" : "secondary"} onPress={() => setKind(option)} />)}
        </View>
        <Pressable onPress={() => choose(null)} style={{ paddingVertical: spacing.sm }}><Text style={type.body}>No referrer</Text></Pressable>
        {filtered.map((item) => <Pressable key={item.id} onPress={() => choose(item)} style={{ paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border }}><Text style={type.body}>{item.name}</Text></Pressable>)}
        <Text style={[type.label, { marginTop: spacing.md }]}>Add new {kind === "architect" ? "architect" : "interior designer"}</Text>
        <TextInput value={name} onChangeText={setName} placeholder="Name or studio" style={{ minHeight: 48, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md }} />
        <Button label={adding ? "Adding…" : "Add and select"} disabled={adding || !name.trim()} onPress={add} />
      </ScrollView>
    </Sheet>
  </View>;
}
