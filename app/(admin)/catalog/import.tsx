// AI Catalog Import — Hansgrohe / Axor / Grohe / Vitra / Geberit
// Steps: pick brand → pick file → Claude extracts → human review → import
import { Feather } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, FlatList, Pressable, StyleSheet, Text, TextInput, View,
} from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Badge, Button, Card, EmptyState } from "@/src/components/ui";
import { toast } from "@/src/components/Toast";
import { api, getToken } from "@/src/api/client";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

const SUPPORTED = ["Hansgrohe", "Axor", "Grohe", "Vitra", "Geberit"] as const;
type Brand = typeof SUPPORTED[number];
const MISSING = "[MISSING DATA]";

type Row = {
  row_id: string; brand: string; name: string; sku: string; category: string;
  finish: string; material: string; dimensions: string; warranty: string;
  mrp: number | string; price: number | string; confidence: number;
  issues: string[]; status: "pending" | "accepted" | "rejected";
};

type Job = {
  id: string; filename: string; source_type: "excel" | "pdf" | "csv";
  supplier_name: string; total_rows: number; accepted_rows: number;
  rejected_rows: number; status: string; rows: Row[]; created_at: string;
  extraction?: {
    pages: number; raw_rows: number; parsed_rows: number;
    images_found: number; images_mapped: number; warnings?: string[];
  };
  certification?: {
    overall_score: number; production_ready: boolean;
    extraction_accuracy: number; sku_accuracy: number; price_accuracy: number;
    category_accuracy: number; variant_accuracy: number; image_accuracy: number;
    duplicate_score: number; missing_data_score: number;
    total_products: number; products_ready: number; products_needing_review: number;
    families_detected: number; duplicates_sku: number;
    missing_images: number; missing_mrp: number; missing_categories: number;
    variant_conflicts?: string[]; category_conflicts?: string[]; warnings?: string[];
  };
};

export default function CatalogImport() {
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [brand, setBrand] = useState<Brand>("Hansgrohe");
  const [current, setCurrent] = useState<Job | null>(null);
  const [uploading, setUploading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [urlInput, setUrlInput] = useState("");

  const loadJobs = useCallback(async () => {
    const list = await api.get<Job[]>("/catalog/imports");
    setJobs(list);
  }, []);
  useEffect(() => { loadJobs(); }, [loadJobs]);

  const pickAndUpload = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        multiple: false, copyToCacheDirectory: true,
        type: [
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "application/vnd.ms-excel", "application/pdf", "text/csv",
        ],
      });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      setUploading(true);
      const token = await getToken();

      const form = new FormData();
      form.append("brand", brand);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      form.append("file", { uri: asset.uri, name: asset.name || "upload", type: asset.mimeType || "application/octet-stream" } as any);

      const r = await fetch(`${api.base}/api/catalog/imports`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const text = await r.text();
      if (!r.ok) {
        toast.error(text || `Upload failed (${r.status})`);
        return;
      }
      const job = JSON.parse(text) as Job;
      setCurrent(job);
      toast.success(`Extracted ${job.total_rows} rows via Claude Sonnet 4.5`);
      loadJobs();
    } catch (e: any) {
      toast.error(e?.message || "Something went wrong");
    } finally {
      setUploading(false);
    }
  };

  const acceptAll = () => {
    if (!current) return;
    const rows = current.rows.map((r) => ({ ...r, status: "accepted" as const }));
    setCurrent({ ...current, rows });
    Promise.all(rows.map((r) =>
      api.patch(`/catalog/imports/${current.id}/rows/${r.row_id}`, { status: "accepted" })
    ));
  };

  const toggleRow = async (r: Row, next: Row["status"]) => {
    if (!current) return;
    const rows = current.rows.map((x) => (x.row_id === r.row_id ? { ...x, status: next } : x));
    setCurrent({ ...current, rows });
    await api.patch(`/catalog/imports/${current.id}/rows/${r.row_id}`, { status: next });
  };

  const editField = async (r: Row, field: keyof Row, value: any) => {
    if (!current) return;
    const rows = current.rows.map((x) => (x.row_id === r.row_id ? { ...x, [field]: value } : x));
    setCurrent({ ...current, rows });
    await api.patch(`/catalog/imports/${current.id}/rows/${r.row_id}`, { [field]: value });
  };

  const importAccepted = async () => {
    if (!current) return;
    setImporting(true);
    try {
      const res = await api.post<{ imported: number; skipped: number }>(`/catalog/imports/${current.id}/approve`);
      toast.success(`Imported ${res.imported} products${res.skipped ? ` · ${res.skipped} skipped` : ""}`);
      setCurrent(null);
      loadJobs();
    } catch (e: any) {
      toast.error(e?.detail || "Import failed");
    } finally {
      setImporting(false);
    }
  };

  // ---------- Review View ----------
  if (current) {
    const accepted = current.rows.filter((r) => r.status === "accepted").length;
    const rejected = current.rows.filter((r) => r.status === "rejected").length;
    const pending = current.rows.filter((r) => r.status === "pending").length;
    const cert = current.certification;
    const ext = current.extraction;
    return (
      <AdminPage
        title={`Review · ${current.supplier_name}`}
        subtitle={`${current.filename} · ${current.total_rows} products · Powered by Forge Ingestion Framework`}
        right={
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Button label="Discard" variant="secondary" onPress={() => setCurrent(null)} testID="discard-import" />
            <Button label="Accept all" icon="check-square" variant="secondary" onPress={acceptAll} testID="accept-all" />
            <Button
              label={importing ? "Importing…" : `Import ${accepted} products`}
              icon="upload-cloud"
              onPress={importAccepted}
              loading={importing}
              disabled={accepted === 0}
              testID="import-accepted"
            />
          </View>
        }
      >
        {cert ? (
          <Card style={styles.certCard}>
            <View style={styles.certHead}>
              <View style={styles.certScore}>
                <Text style={styles.certScoreNum}>{cert.overall_score}%</Text>
                <Text style={styles.certScoreLabel}>Certification</Text>
              </View>
              <View style={{ flex: 1, gap: 4 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={type.titleLg}>{cert.production_ready ? "Production ready" : "Needs human review"}</Text>
                  <Badge tone={cert.production_ready ? "success" : "warning"} label={cert.production_ready ? "CERTIFIED" : "REVIEW"} />
                </View>
                <Text style={type.bodyMuted}>
                  {cert.products_ready} of {cert.total_products} products fully validated · {cert.families_detected} product families detected
                  {ext ? ` · ${ext.images_mapped}/${ext.images_found} images mapped` : ""}
                </Text>
              </View>
            </View>

            <View style={styles.scoresGrid}>
              {[
                ["SKU", cert.sku_accuracy], ["Price", cert.price_accuracy],
                ["Category", cert.category_accuracy], ["Variants", cert.variant_accuracy],
                ["Images", cert.image_accuracy], ["Duplicates", cert.duplicate_score],
              ].map(([k, v]) => (
                <View key={String(k)} style={styles.scorePill}>
                  <Text style={type.caption}>{k as string}</Text>
                  <Text style={[type.mono, { fontWeight: "700", color: (v as number) >= 90 ? colors.success : (v as number) >= 70 ? colors.warning : colors.error }]}>{v}%</Text>
                </View>
              ))}
            </View>

            {cert.duplicates_sku || cert.missing_mrp || cert.missing_images || cert.missing_categories ? (
              <View style={styles.issueSummary}>
                {cert.duplicates_sku ? <Badge tone="error" label={`${cert.duplicates_sku} duplicate SKUs`} /> : null}
                {cert.missing_mrp ? <Badge tone="warning" label={`${cert.missing_mrp} missing MRP`} /> : null}
                {cert.missing_categories ? <Badge tone="warning" label={`${cert.missing_categories} missing category`} /> : null}
                {cert.missing_images ? <Badge tone="warning" label={`${cert.missing_images} without image`} /> : null}
              </View>
            ) : null}
          </Card>
        ) : null}

        <View style={{ flexDirection: "row", gap: 8 }}>
          <Badge tone="success" label={`${accepted} accepted`} />
          <Badge tone="warning" label={`${pending} pending`} />
          <Badge tone="error" label={`${rejected} rejected`} />
        </View>

        <FlatList
          data={current.rows}
          keyExtractor={(r) => r.row_id}
          scrollEnabled={false}
          contentContainerStyle={{ gap: spacing.sm }}
          renderItem={({ item }) => (
            <Card style={styles.rowCard}>
              <View style={styles.rowHead}>
                <View style={{ flex: 1, gap: 2 }}>
                  <TextInput
                    testID={`row-name-${item.row_id}`}
                    value={item.name === MISSING ? "" : item.name}
                    onChangeText={(v) => editField(item, "name", v)}
                    placeholder="Product name"
                    placeholderTextColor={colors.onSurfaceMuted}
                    style={styles.rowNameInput}
                  />
                  <View style={{ flexDirection: "row", gap: 6, alignItems: "center" }}>
                    <Text style={type.mono}>{item.sku === MISSING ? "no-sku" : item.sku}</Text>
                    <Text style={type.caption}>· {item.category}</Text>
                    {item.confidence < 0.7 ? <Badge tone="warning" label={`${Math.round(item.confidence * 100)}%`} /> : null}
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: 6 }}>
                  <Pressable
                    testID={`reject-${item.row_id}`}
                    onPress={() => toggleRow(item, "rejected")}
                    style={[styles.iconBtn, item.status === "rejected" && { backgroundColor: colors.errorBg }]}
                  >
                    <Feather name="x" size={14} color={item.status === "rejected" ? colors.error : colors.onSurfaceMuted} />
                  </Pressable>
                  <Pressable
                    testID={`accept-${item.row_id}`}
                    onPress={() => toggleRow(item, "accepted")}
                    style={[styles.iconBtn, item.status === "accepted" && { backgroundColor: colors.successBg }]}
                  >
                    <Feather name="check" size={14} color={item.status === "accepted" ? colors.success : colors.onSurfaceMuted} />
                  </Pressable>
                </View>
              </View>

              <View style={styles.rowFields}>
                <FieldInput label="MRP ₹" value={item.mrp} onChange={(v) => editField(item, "mrp", v === "" ? MISSING : Number(v))} keyboardType="decimal-pad" testID={`mrp-${item.row_id}`} />
                <FieldInput label="PRICE ₹" value={item.price} onChange={(v) => editField(item, "price", v === "" ? MISSING : Number(v))} keyboardType="decimal-pad" testID={`price-${item.row_id}`} />
                <FieldInput label="FINISH" value={item.finish} onChange={(v) => editField(item, "finish", v || MISSING)} />
                <FieldInput label="MATERIAL" value={item.material} onChange={(v) => editField(item, "material", v || MISSING)} />
              </View>

              {item.issues?.length ? (
                <View style={styles.issueRow}>
                  <Feather name="alert-triangle" size={12} color={colors.warning} />
                  <Text style={[type.caption, { color: colors.warning, flex: 1 }]} numberOfLines={2}>
                    {item.issues.join(" · ")}
                  </Text>
                </View>
              ) : null}
            </Card>
          )}
        />
      </AdminPage>
    );
  }

  const importFromUrl = async () => {
    if (!urlInput) return;
    setUploading(true);
    try {
      const job = await api.post<Job>("/catalog/imports/from-url", { brand, url: urlInput });
      setCurrent(job);
      toast.success(`Extracted ${job.total_rows} products · ${job.certification?.overall_score}% certified`);
      loadJobs();
      setUrlInput("");
    } catch (e: any) {
      toast.error(e?.detail || "Import failed");
    } finally {
      setUploading(false);
    }
  };

  // ---------- List / Upload View ----------
  return (
    <AdminPage
      title="AI Catalog Import"
      subtitle="Upload supplier price-lists — Claude Sonnet 4.5 normalizes rows in seconds. Only 5 supplier brands are supported."
      right={
        <Pressable
          testID="back-to-catalog"
          onPress={() => router.back()}
          style={{ flexDirection: "row", alignItems: "center", gap: 4 }}
        >
          <Feather name="chevron-left" size={16} color={colors.onSurface} />
          <Text style={{ fontSize: 13, fontWeight: "500" }}>Back</Text>
        </Pressable>
      }
    >
      {/* Uploader */}
      <Card>
        <Text style={type.overline}>Step 1 · Supplier</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
          {SUPPORTED.map((b) => (
            <Pressable
              key={b}
              testID={`brand-${b}`}
              onPress={() => setBrand(b)}
              style={[styles.brandChip, brand === b && styles.brandChipActive]}
            >
              <Text style={{ fontSize: 13, fontWeight: "700", color: brand === b ? colors.onBrand : colors.onSurface }}>{b}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={[type.overline, { marginTop: spacing.lg }]}>Step 2 · File</Text>
        <Pressable
          testID="upload-file"
          onPress={pickAndUpload}
          style={[styles.dropzone, uploading && { opacity: 0.6 }]}
        >
          {uploading ? (
            <>
              <ActivityIndicator color={colors.brand} />
              <Text style={[type.body, { marginTop: 8, fontWeight: "600" }]}>Claude is reading the catalog…</Text>
              <Text style={type.caption}>Extraction, normalization and classification typically take 3–15 seconds.</Text>
            </>
          ) : (
            <>
              <View style={styles.dropIcon}><Feather name="upload-cloud" size={24} color={colors.brand} /></View>
              <Text style={[type.titleMd, { marginTop: 12 }]}>Upload {brand} supplier catalog</Text>
              <Text style={[type.bodyMuted, { textAlign: "center", maxWidth: 380 }]}>
                Excel (.xlsx / .xls), PDF or CSV. The supplier file is always the source of truth — nothing is invented.
              </Text>
              <View style={{ flexDirection: "row", gap: 6, marginTop: 12, flexWrap: "wrap", justifyContent: "center" }}>
                <Badge label=".xlsx" />
                <Badge label=".xls" />
                <Badge label=".pdf" />
                <Badge label=".csv" />
              </View>
            </>
          )}
        </Pressable>

        <Text style={[type.overline, { marginTop: spacing.lg }]}>Or import from URL</Text>
        <View style={{ flexDirection: "row", gap: 8, marginTop: 8 }}>
          <TextInput
            testID="url-input"
            value={urlInput}
            onChangeText={setUrlInput}
            placeholder="https://supplier.com/2026-pricelist.pdf"
            placeholderTextColor={colors.onSurfaceMuted}
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.urlInput}
          />
          <Button label="Fetch" icon="link" onPress={importFromUrl} disabled={!urlInput || uploading} testID="fetch-url" />
        </View>
      </Card>

      {/* Recent jobs */}
      <View>
        <Text style={type.overline}>Recent imports</Text>
        <View style={{ height: 8 }} />
        {!jobs ? null : jobs.length === 0 ? (
          <EmptyState icon="database" title="No imports yet" subtitle="Upload your first supplier catalog to see the pipeline in action." />
        ) : (
          <Card style={{ padding: 0 }}>
            {jobs.map((j, i) => (
              <Pressable
                key={j.id}
                testID={`job-${j.id}`}
                onPress={async () => {
                  const full = await api.get<Job>(`/catalog/imports/${j.id}`);
                  setCurrent(full);
                }}
                style={({ pressed }) => [styles.jobRow, {
                  borderTopWidth: i === 0 ? 0 : StyleSheet.hairlineWidth, borderColor: colors.border,
                  backgroundColor: pressed ? colors.surfaceTertiary : "transparent",
                }]}
              >
                <View style={styles.jobIcon}>
                  <Feather name={j.source_type === "pdf" ? "file-text" : j.source_type === "csv" ? "database" : "grid"} size={16} color={colors.onSurface} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: "600" }} numberOfLines={1}>{j.filename}</Text>
                  <Text style={type.caption}>
                    {j.supplier_name} · {j.total_rows} rows · {new Date(j.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </Text>
                </View>
                <Badge
                  tone={j.status === "imported" ? "success" : j.status === "classified" ? "warning" : "neutral"}
                  label={j.status}
                />
              </Pressable>
            ))}
          </Card>
        )}
      </View>
    </AdminPage>
  );
}

function FieldInput({ label, value, onChange, keyboardType = "default", testID }: {
  label: string; value: string | number; onChange: (v: string) => void;
  keyboardType?: "default" | "decimal-pad"; testID?: string;
}) {
  const display = value === MISSING || value === undefined || value === null ? "" : String(value);
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={display}
        onChangeText={onChange}
        keyboardType={keyboardType}
        placeholder={MISSING}
        placeholderTextColor={colors.warning}
        style={styles.fieldInput}
        selectTextOnFocus
        testID={testID}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  brandChip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  brandChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  dropzone: {
    marginTop: 8, alignItems: "center", justifyContent: "center", gap: 4,
    padding: spacing.xl, borderRadius: radius.md, borderWidth: 2, borderColor: colors.border,
    borderStyle: "dashed", backgroundColor: colors.surfaceTertiary,
  },
  dropIcon: {
    width: 48, height: 48, borderRadius: 999, backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  jobRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md,
  },
  jobIcon: {
    width: 36, height: 36, borderRadius: 8, backgroundColor: colors.surfaceTertiary,
    alignItems: "center", justifyContent: "center",
  },
  rowCard: { padding: spacing.md, gap: spacing.sm },
  rowHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  rowNameInput: {
    fontSize: 15, fontWeight: "700", color: colors.onSurface, padding: 0, paddingVertical: 2,
  },
  iconBtn: {
    width: 30, height: 30, borderRadius: 6, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary,
  },
  rowFields: {
    flexDirection: "row", gap: 6, flexWrap: "wrap",
  },
  field: {
    borderWidth: 1, borderColor: colors.border, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4,
    minWidth: 110, flex: 1, backgroundColor: colors.surface,
  },
  fieldLabel: { fontSize: 9, color: colors.onSurfaceMuted, fontWeight: "700", letterSpacing: 0.5 },
  fieldInput: {
    fontSize: 13, color: colors.onSurface, padding: 0, minWidth: 60,
  },
  issueRow: {
    flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.warningBg,
    padding: 8, borderRadius: 6,
  },
  urlInput: {
    flex: 1, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, color: colors.onSurface,
  },
  certCard: {
    padding: spacing.lg, gap: spacing.md, borderColor: colors.brandTertiary,
  },
  certHead: { flexDirection: "row", alignItems: "center", gap: spacing.lg },
  certScore: {
    width: 96, height: 96, borderRadius: 48, backgroundColor: colors.surfaceInverse,
    alignItems: "center", justifyContent: "center",
  },
  certScoreNum: { color: colors.onBrand, fontSize: 26, fontWeight: "800", letterSpacing: -0.5 },
  certScoreLabel: { color: "rgba(255,255,255,0.7)", fontSize: 10, letterSpacing: 1.2, fontWeight: "600" },
  scoresGrid: {
    flexDirection: "row", gap: 8, flexWrap: "wrap",
  },
  scorePill: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 999, backgroundColor: colors.surfaceTertiary,
  },
  issueSummary: {
    flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 4,
  },
});
