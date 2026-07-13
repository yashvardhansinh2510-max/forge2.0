// Customer Portal — Quotation Detail (read-only). Line items, status,
// primary "Download PDF" action, plus previous-revision downloads and
// brand-wise downloads where applicable. No editing of any kind — this is
// a document viewer, not the Quotation Builder.
//
// Route note: lives at (customer)/quotes/[id] rather than
// (customer)/quotations/[id] — see quotes/index.tsx header comment for why
// (avoids a real URL collision with (admin)/quotations/[id]).
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { Button, Card, PageHeader, Skeleton, StatusBadge } from "@/src/components/ui";
import { openPortalPdf } from "@/src/utils/portalPdf";
import { colors, money, spacing, type } from "@/src/theme/tokens";

type Item = { id: string; name: string; sku: string; qty: number; unit_price: number; room?: string };
type Revision = { revision_no: number; created_at: string; reason?: string };
type BrandGroup = { brand_id: string | null; brand_name: string; item_count: number; subtotal: number };
type Detail = {
  id: string; number: string; status: string; created_at: string; valid_until?: string;
  items: Item[]; subtotal: number; grand_total: number; project_name?: string;
  revisions: Revision[]; brands: BrandGroup[];
};

export default function CustomerQuotationDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [doc, setDoc] = useState<Detail | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.get<Detail>(`/portal/quotations/${id}`).then(setDoc).catch(() => setDoc(null));
  }, [id]);

  const download = async (key: string, path: string, filename: string) => {
    setDownloading(key);
    await openPortalPdf(path, filename);
    setDownloading(null);
  };

  if (!doc) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
        <PageHeader title="Quotation" back={() => router.back()} />
        <View style={{ padding: spacing.xl, gap: spacing.md }}>
          <Skeleton w="50%" />
          <Skeleton w="90%" h={80} />
          <Skeleton w="70%" h={120} />
        </View>
      </SafeAreaView>
    );
  }

  const showBrandSection = doc.brands && doc.brands.length > 1;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <PageHeader title={doc.number} subtitle={doc.project_name || undefined} back={() => router.back()} />
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg, paddingBottom: 40 }}>
        {/* Summary */}
        <Card style={{ gap: spacing.md }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
            <View>
              <Text style={type.caption}>
                {new Date(doc.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}
              </Text>
              {doc.valid_until ? (
                <Text style={type.caption}>Valid until {new Date(doc.valid_until).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</Text>
              ) : null}
            </View>
            <StatusBadge status={doc.status} />
          </View>
          <View>
            <Text style={type.caption}>Grand total</Text>
            <Text style={{ fontSize: 28, fontWeight: "700", fontVariant: ["tabular-nums"] }}>{money(doc.grand_total)}</Text>
          </View>
          <Button
            testID="download-latest-pdf"
            label="Download quotation PDF"
            icon="download"
            fullWidth
            loading={downloading === "latest"}
            onPress={() => download("latest", `/quotations/${doc.id}/portal-pdf`, `${doc.number}.pdf`)}
          />
        </Card>

        {/* Line items */}
        <View>
          <Text style={type.overline}>Items ({doc.items.length})</Text>
        </View>
        <Card style={{ gap: spacing.sm }}>
          {doc.items.map((item, idx) => (
            <View key={item.id}>
              {idx > 0 ? <View style={{ height: 1, backgroundColor: colors.border, marginVertical: spacing.sm }} /> : null}
              <View style={{ flexDirection: "row", justifyContent: "space-between", gap: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Text style={type.bodyStrong} numberOfLines={2}>{item.name}</Text>
                  <Text style={type.caption}>{item.sku}{item.room ? ` · ${item.room}` : ""} · Qty {item.qty}</Text>
                </View>
                <Text style={[type.bodyStrong, { fontVariant: ["tabular-nums"] }]}>{money(item.qty * item.unit_price)}</Text>
              </View>
            </View>
          ))}
        </Card>

        {/* Revisions */}
        {doc.revisions && doc.revisions.length > 0 ? (
          <>
            <View>
              <Text style={type.overline}>Previous revisions</Text>
            </View>
            <Card style={{ gap: spacing.sm }}>
              {doc.revisions.map((rev, idx) => (
                <View key={rev.revision_no}>
                  {idx > 0 ? <View style={{ height: 1, backgroundColor: colors.border, marginVertical: spacing.sm }} /> : null}
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                    <View style={{ flex: 1 }}>
                      <Text style={type.bodyStrong}>Revision {rev.revision_no}</Text>
                      <Text style={type.caption}>
                        {new Date(rev.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                        {rev.reason ? ` · ${rev.reason}` : ""}
                      </Text>
                    </View>
                    <Button
                      testID={`download-revision-${rev.revision_no}`}
                      label="Download"
                      icon="download"
                      size="sm"
                      variant="secondary"
                      loading={downloading === `rev-${rev.revision_no}`}
                      onPress={() => download(`rev-${rev.revision_no}`, `/quotations/${doc.id}/portal-pdf/revision/${rev.revision_no}`, `${doc.number}-rev${rev.revision_no}.pdf`)}
                    />
                  </View>
                </View>
              ))}
            </Card>
          </>
        ) : null}

        {/* Brand-wise downloads */}
        {showBrandSection ? (
          <>
            <View>
              <Text style={type.overline}>Download by brand</Text>
            </View>
            <Card style={{ gap: spacing.sm }}>
              {doc.brands.map((b, idx) => {
                const brandKey = b.brand_id ?? "unassigned";
                return (
                  <View key={brandKey}>
                    {idx > 0 ? <View style={{ height: 1, backgroundColor: colors.border, marginVertical: spacing.sm }} /> : null}
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                      <View style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 8 }}>
                        <Feather name="tag" size={14} color={colors.onSurfaceMuted} />
                        <View>
                          <Text style={type.bodyStrong}>{b.brand_name}</Text>
                          <Text style={type.caption}>{b.item_count} item{b.item_count === 1 ? "" : "s"} · {money(b.subtotal)}</Text>
                        </View>
                      </View>
                      <Button
                        testID={`download-brand-${brandKey}`}
                        label="Download"
                        icon="download"
                        size="sm"
                        variant="secondary"
                        loading={downloading === `brand-${brandKey}`}
                        onPress={() => download(`brand-${brandKey}`, `/quotations/${doc.id}/portal-pdf/brand/${brandKey}`, `${doc.number}-${b.brand_name}.pdf`)}
                      />
                    </View>
                  </View>
                );
              })}
            </Card>
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}
