// Log Walk-in — Phase 4 (2026-07-30). Dedicated full-screen create form
// (not a popup), matching customers/new.tsx pattern. Duplicate detection
// per spec: as the phone is typed, check-duplicate looks up an existing
// Customer by phone/alternate_phone before submit — backend does the
// authoritative check again on POST regardless.
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { walkinsApi } from "@/src/api/walkins";
import { toast } from "@/src/components/Toast";
import { Button, Card, Chip, PageHeader, TextField } from "@/src/components/ui";
import { useFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, spacing, type } from "@/src/theme/tokens";

export default function NewWalkIn() {
  const router = useRouter();
  const { floors, selectedFloorId } = useFloorAccess();
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [altPhone, setAltPhone] = useState("");
  const [email, setEmail] = useState("");
  const [budget, setBudget] = useState("");
  const [notes, setNotes] = useState("");
  const [products, setProducts] = useState("");
  const [source, setSource] = useState("Walk-in");
  const [sources, setSources] = useState<string[]>(["Walk-in", "Reference", "Architect", "Builder", "Social Media", "Existing Customer", "Other"]);
  const [floorId, setFloorId] = useState(selectedFloorId || floors[0]?.id || "");
  const [existingCustomer, setExistingCustomer] = useState<{ id: string; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    walkinsApi.listSources().then((r) => setSources(r.sources)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!floorId && (selectedFloorId || floors[0]?.id)) setFloorId(selectedFloorId || floors[0]?.id);
  }, [selectedFloorId, floors, floorId]);

  useEffect(() => {
    const digits = phone.replace(/\D/g, "");
    if (digits.length < 10) { setExistingCustomer(null); return; }
    const t = setTimeout(() => {
      walkinsApi.checkDuplicate(phone, altPhone).then((r) => {
        setExistingCustomer(r.customer ? { id: r.customer.id, name: r.customer.name } : null);
      }).catch(() => {});
    }, 400);
    return () => clearTimeout(t);
  }, [phone, altPhone]);

  const save = async () => {
    if (!name.trim()) { setError("Name is required"); toast.error("Enter the customer's name"); return; }
    if (!phone.trim()) { setError("Phone is required"); toast.error("Enter a phone number"); return; }
    if (!floorId) { setError("Department is required"); toast.error("Select an interested department"); return; }
    setSaving(true);
    try {
      const created = await walkinsApi.create({
        customer_name: name.trim(), customer_phone: phone.trim(),
        alternate_phone: altPhone.trim() || undefined, email: email.trim() || undefined,
        source, floor_id: floorId,
        interested_products: products.split(",").map((p) => p.trim()).filter(Boolean),
        budget: budget ? Number(budget) : undefined, notes: notes.trim() || undefined,
      });
      toast.success("Walk-in logged");
      router.replace(`/(admin)/walkins/${created.id}` as any);
    } catch (e: any) {
      toast.error(e?.detail || "Could not save Walk-in");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1 }} edges={["top"]}>
      <PageHeader title="Log Walk-in" overline="CRM" back={() => router.back()} />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }}>
          <TextField label="Customer Name *" value={name} onChangeText={setName} placeholder="Full name" testID="walkin-name" />
          <TextField label="Phone *" value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="10-digit mobile" testID="walkin-phone" />
          {existingCustomer ? (
            <Card variant="outlined" style={{ backgroundColor: colors.brandTint }}>
              <Text style={type.bodySm}>Existing customer found: <Text style={type.bodyStrong}>{existingCustomer.name}</Text>. This walk-in will be linked to their profile — no duplicate will be created.</Text>
            </Card>
          ) : null}
          <TextField label="Alternate Phone" value={altPhone} onChangeText={setAltPhone} keyboardType="phone-pad" placeholder="Optional" testID="walkin-alt-phone" />
          <TextField label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" placeholder="Optional" testID="walkin-email" />

          <Text style={type.bodyStrong}>Interested Department *</Text>
          <View style={{ flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" }}>
            {floors.map((f) => (
              <Chip key={f.id} label={f.name} active={floorId === f.id} onPress={() => setFloorId(f.id)} testID={`walkin-floor-${f.id}`} />
            ))}
          </View>

          <Text style={type.bodyStrong}>Source</Text>
          <View style={{ flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" }}>
            {sources.map((s) => (
              <Chip key={s} label={s} active={source === s} onPress={() => setSource(s)} testID={`walkin-source-${s}`} />
            ))}
          </View>

          <TextField label="Interested Products" value={products} onChangeText={setProducts} placeholder="Comma-separated, e.g. Vitrified Tiles, Granite" testID="walkin-products" />
          <TextField label="Budget (₹)" value={budget} onChangeText={setBudget} keyboardType="numeric" placeholder="Optional" testID="walkin-budget" />
          <TextField label="Notes" value={notes} onChangeText={setNotes} placeholder="Optional" multiline numberOfLines={3} testID="walkin-notes" />

          {error ? <Text style={[type.bodySm, { color: colors.error }]}>{error}</Text> : null}
          <Button label="Log Walk-in" onPress={save} loading={saving} testID="walkin-save-btn" />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
