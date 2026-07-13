// Add Customer — create-customer form. Was previously missing: the
// "Add Customer" button on the list screen navigated to this route with no
// screen backing it (Expo Router's [id].tsx would have caught "new" as a
// literal customer id and tried to fetch a workspace for a nonexistent
// customer). Backend already fully supports POST /customers — this screen
// was simply never built. DS-aligned with the rest of this folder
// (theme/tokens + components/ui, matching customers/index.tsx + [id].tsx).
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView, Platform, ScrollView, Text, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import {
  Button, Chip, PageHeader, TextField,
} from "@/src/components/ui";
import { toast } from "@/src/components/Toast";
import { colors, spacing, type } from "@/src/theme/tokens";

type Tier = "retail" | "trade" | "vip";

export default function NewCustomer() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [city, setCity] = useState("");
  const [address, setAddress] = useState("");
  const [gstin, setGstin] = useState("");
  const [tier, setTier] = useState<Tier>("retail");
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!name.trim()) {
      setError("Name is required");
      toast.error("Enter a customer name");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        company: company.trim() || null,
        email: email.trim() || null,
        phone: phone.trim() || null,
        city: city.trim() || null,
        address: address.trim() || null,
        gstin: gstin.trim() || null,
        tier,
      };
      const created = await api.post<{ id: string }>("/customers", payload);
      toast.success("Customer added");
      router.replace(`/(admin)/customers/${created.id}` as any);
    } catch (e: any) {
      toast.error(e?.detail || "Could not save customer");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <PageHeader title="Add Customer" overline="CRM" back={() => router.back()} />
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={{ flex: 1 }}
        keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
      >
        <ScrollView
          contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg, paddingBottom: spacing.xxxl }}
          keyboardShouldPersistTaps="handled"
        >
          <TextField
            label="Name *"
            placeholder="e.g. Rajesh Malhotra"
            value={name}
            onChangeText={(v) => { setName(v); setError(null); }}
            error={error}
            autoFocus
            testID="new-customer-name"
          />
          <TextField
            label="Company"
            placeholder="Business name (optional)"
            value={company}
            onChangeText={setCompany}
            testID="new-customer-company"
          />
          <TextField
            label="Email"
            placeholder="name@example.com"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            testID="new-customer-email"
          />
          <TextField
            label="Phone"
            placeholder="+91 98xxxxxxxx"
            value={phone}
            onChangeText={setPhone}
            keyboardType="phone-pad"
            testID="new-customer-phone"
          />
          <TextField
            label="City"
            placeholder="e.g. Ahmedabad"
            value={city}
            onChangeText={setCity}
            testID="new-customer-city"
          />
          <TextField
            label="Address"
            placeholder="Street, area, pincode"
            value={address}
            onChangeText={setAddress}
            multiline
            numberOfLines={3}
            style={{ minHeight: 72, textAlignVertical: "top" }}
            testID="new-customer-address"
          />
          <TextField
            label="GSTIN"
            placeholder="Optional, for trade/VIP invoicing"
            value={gstin}
            onChangeText={setGstin}
            autoCapitalize="characters"
            testID="new-customer-gstin"
          />

          <View style={{ gap: 6 }}>
            <Text style={type.label}>Tier</Text>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              {(["retail", "trade", "vip"] as Tier[]).map((t) => (
                <Chip
                  key={t}
                  label={t.charAt(0).toUpperCase() + t.slice(1)}
                  active={tier === t}
                  onPress={() => setTier(t)}
                  testID={`new-customer-tier-${t}`}
                />
              ))}
            </View>
          </View>

          <Button
            label={saving ? "Saving…" : "Save Customer"}
            variant="primary"
            size="lg"
            icon="check"
            disabled={saving}
            onPress={save}
            testID="new-customer-save"
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
