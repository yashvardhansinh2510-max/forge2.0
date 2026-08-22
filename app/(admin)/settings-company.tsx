// Settings > Company -- name/tagline/contact/logo. Previously these were
// hardcoded constants (theme/tokens.ts `brand`) with no way to change them
// at all. Editing requires admin+; other roles see a read-only view.
import { Feather } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Image, ScrollView, Text, View } from "react-native";

import { api } from "@/src/api/client";
import { AdminPage } from "@/src/components/AdminPage";
import { toast } from "@/src/components/Toast";
import { Button, Card, TextField } from "@/src/components/ui";
import { useAuth } from "@/src/state/auth";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type Company = {
  name: string; tagline: string; phone: string; email: string;
  address?: string | null; gstin?: string | null; logo_base64?: string | null;
};

export default function SettingsCompany() {
  const router = useRouter();
  const { staff } = useAuth();
  const canEdit = staff?.role === "owner" || staff?.role === "admin";
  const [form, setForm] = useState<Company | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<Company>("/settings/company").then(setForm).catch(() => setForm(null));
  }, []);

  const set = (k: keyof Company) => (v: string) => setForm((f) => (f ? { ...f, [k]: v } : f));

  const pickLogo = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) { toast.show("Photo library permission is needed"); return; }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"], quality: 0.8, base64: true, allowsEditing: true, aspect: [3, 1],
    });
    if (result.canceled || !result.assets?.[0]?.base64) return;
    const asset = result.assets[0];
    const mime = asset.mimeType || "image/png";
    setForm((f) => (f ? { ...f, logo_base64: `data:${mime};base64,${asset.base64}` } : f));
  };

  const save = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const updated = await api.put<Company>("/settings/company", form);
      setForm(updated);
      toast.show("Company profile saved");
    } catch (e: any) {
      toast.show(e?.message || "Couldn't save");
    } finally {
      setSaving(false);
    }
  };

  if (!form) {
    return <AdminPage title="Company" back={() => router.back()}><View /></AdminPage>;
  }

  return (
    <AdminPage title="Company" subtitle={canEdit ? undefined : "View only -- admin role required to edit"} back={() => router.back()}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: spacing.lg }}>
        <Card style={{ alignItems: "center", gap: spacing.sm }}>
          {form.logo_base64 ? (
            <Image source={{ uri: form.logo_base64 }} style={{ width: 160, height: 54, borderRadius: radius.sm }} resizeMode="contain" />
          ) : (
            <View style={{ width: 160, height: 54, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" }}>
              <Feather name="image" size={20} color={colors.onSurfaceMuted} />
            </View>
          )}
          {canEdit ? (
            <Button testID="pick-logo-btn" label="Change logo" icon="upload" size="sm" variant="secondary" onPress={pickLogo} />
          ) : null}
          <Text style={type.caption}>Shown in-app only for now -- quotation PDFs keep their existing printed header.</Text>
        </Card>

        <Card style={{ gap: spacing.md }}>
          <TextField testID="company-name-input" label="Company name" value={form.name} onChangeText={set("name")} editable={canEdit} />
          <TextField testID="company-tagline-input" label="Tagline" value={form.tagline} onChangeText={set("tagline")} editable={canEdit} />
          <TextField testID="company-phone-input" label="Phone" value={form.phone} onChangeText={set("phone")} editable={canEdit} keyboardType="phone-pad" />
          <TextField testID="company-email-input" label="Email" value={form.email} onChangeText={set("email")} editable={canEdit} keyboardType="email-address" autoCapitalize="none" />
          <TextField testID="company-address-input" label="Address (optional)" value={form.address || ""} onChangeText={set("address")} editable={canEdit} multiline />
          <TextField testID="company-gstin-input" label="GSTIN (optional)" value={form.gstin || ""} onChangeText={set("gstin")} editable={canEdit} autoCapitalize="characters" />
        </Card>

        {canEdit ? (
          <Button testID="save-company-btn" label="Save changes" icon="check" loading={saving} onPress={save} fullWidth />
        ) : null}
      </ScrollView>
    </AdminPage>
  );
}
